"""
Tasks related to files.
"""

import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

import requests

from core import analytics
from core.models import AiFileJob, AiJobStatusChoices, AiJobTypeChoices, File
from core.utils import format_transcript, generate_download_file_url
from core.webhook_models import WhisperXResponse

from dictaphone.celery_app import app

logger = logging.getLogger(__name__)


@app.task
def process_file_deletion(file_id):
    """
    Process the deletion of a file.
    Definitely delete it in the database.
    Delete the files from the storage.
    """
    logger.info("Processing file deletion for %s", file_id)
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    if file.hard_deleted_at is None:
        logger.error("To process a file deletion, it must be hard deleted first.")
        return

    logger.info("Deleting file %s", file.file_key)
    default_storage.delete(file.file_key)

    file.delete()


@app.task
def call_transcribe_service(file_id):
    """
    Call the transcribe service for a given file.
    """
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    ai_transcribe_job = AiFileJob.objects.create(
        remote_job_id=None,
        file=file,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )

    try:
        response = requests.post(
            settings.AI_SERVICE_URL + "async-jobs/transcribe/",
            json={
                "user_sub": file.creator.sub,
                "language": "fr",
                "cloud_storage_url": generate_download_file_url(
                    file, expires_in=60 * 60 * 24, override_domain=False
                ),
            },
            headers={
                "Authorization": f"Bearer {settings.AI_SERVICE_API_KEY}",
            },
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error("Creating transcription job failed for file %s: %s", file_id, e)
        ai_transcribe_job.status = AiJobStatusChoices.FAILED
        ai_transcribe_job.save()
        raise e

    data = response.json()

    ai_transcribe_job.remote_job_id = data["job_id"]
    ai_transcribe_job.save()

    logger.info("Transcription job created for file %s", file_id)


@app.task
def handle_transcript_received(remote_job_id, url):
    """
    Store the transcript and call the summarize service for a given file.
    """
    ai_transcript_job = AiFileJob.objects.filter(
        remote_job_id=remote_job_id, type=AiJobTypeChoices.TRANSCRIPT
    ).first()
    if not ai_transcript_job:
        logger.warning("No AI file job found for job ID: %s", remote_job_id)
        return

    file = ai_transcript_job.file

    logger.info("Storing transcript for file %s & url %s", file.id, url)
    # could be streamed to S3 later
    response = requests.get(url, timeout=(10, 20))
    response.raise_for_status()
    transcript = WhisperXResponse(**response.json())

    s3_client = default_storage.connection.meta.client
    s3_client.put_object(
        Bucket=default_storage.bucket_name,
        Key=ai_transcript_job.key,
        Body=response.content,
        ContentType="application/json",
    )
    logger.info("Transcript stored for file %s & url %s", file.id, url)
    ai_transcript_job.status = AiJobStatusChoices.SUCCESS
    ai_transcript_job.save()

    analytics.capture_event(
        analytics.EventName.TRANSCRIPT_GENERATION_SUCCESS,
        user=ai_transcript_job.file.creator,
        properties={
            "generation_time_seconds": (
                timezone.now() - ai_transcript_job.created_at
            ).total_seconds(),
            "ai_file_job_id": ai_transcript_job.id,
            "file_id": ai_transcript_job.file.id,
            "transcript_size": len(response.content),
            "file_duration_seconds": ai_transcript_job.file.duration_seconds,
        },
    )

    create_document_in_docs.apply_async(args=[ai_transcript_job.id])

    ai_summary_job = AiFileJob.objects.create(
        remote_job_id=None,
        file=file,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    )

    try:
        summary_response = requests.post(
            settings.AI_SERVICE_URL + "async-jobs/summarize/",
            json={
                "user_sub": file.creator.sub,
                "language": "fr",
                "content": format_transcript(transcript),
            },
            headers={
                "Authorization": f"Bearer {settings.AI_SERVICE_API_KEY}",
            },
            timeout=10,
        )
        summary_response.raise_for_status()
    except Exception as e:
        logger.error("Creating summary job failed for file %s: %s", file.id, e)
        ai_summary_job.status = AiJobStatusChoices.FAILED
        ai_summary_job.save()
        raise e

    ai_summary_job.remote_job_id = summary_response.json()["job_id"]
    ai_summary_job.save()

    logger.info("Summary job created for file %s", file.id)


@app.task
def store_summary(remote_job_id, url):
    """
    Store the summary of a given file.
    """
    ai_summary_job = AiFileJob.objects.filter(
        remote_job_id=remote_job_id, type=AiJobTypeChoices.SUMMARIZE
    ).first()
    if not ai_summary_job:
        logger.warning("No AI file job found for job ID: %s", remote_job_id)
        return

    file = ai_summary_job.file

    logger.info("Storing summary for file %s & url %s", file.id, url)
    # could be streamed to S3 later
    response = requests.get(url, timeout=(10, 20))
    response.raise_for_status()

    s3_client = default_storage.connection.meta.client
    s3_client.put_object(
        Bucket=default_storage.bucket_name,
        Key=ai_summary_job.key,
        Body=response.content,
        ContentType="text/plain",
    )
    logger.info("Summary stored for file %s & url %s", file.id, url)
    ai_summary_job.status = AiJobStatusChoices.SUCCESS
    ai_summary_job.save()


@app.task
def create_document_in_docs(ai_job_id):
    """
    Create a document in Docs for a given file.
    """
    ai_job = AiFileJob.objects.prefetch_related("file", "file__creator").get(
        pk=ai_job_id
    )
    if ai_job is None or ai_job.type != AiJobTypeChoices.TRANSCRIPT:
        logger.warning("No AI file job found for job ID: %s", ai_job_id)
        return

    if ai_job.docs_app_id is not None:
        logger.info("Document already exists in Docs for file %s", ai_job.file.id)
        return

    content = ai_job.to_markdown(ai_job.file.creator.language)

    response = requests.post(
        urljoin(settings.DOCS_BASE_URL, "/api/v1.0/documents/create-for-owner/"),
        json={
            "title": ai_job.file.title,
            "content": content,
            "email": ai_job.file.creator.email,
            "sub": ai_job.file.creator.sub,
        },
        headers={
            "Authorization": f"Bearer {settings.DOCS_SERVER_TO_SERVER_API_KEY}",
        },
        timeout=20,
    )
    if response.status_code != 201:
        logger.error(
            "Failed to create document in Docs for file %s: %s",
            ai_job.file.id,
            response.text,
        )
        response.raise_for_status()

    docs_app_id = response.json()["id"]
    logger.info(
        "Document created in Docs for file %s => %s (in docs)",
        ai_job.file.id,
        docs_app_id,
    )
    ai_job.docs_app_id = docs_app_id
    ai_job.save()
