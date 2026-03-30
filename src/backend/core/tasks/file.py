"""
Tasks related to files.
"""

import logging

from django.conf import settings
from django.core.files.storage import default_storage

import requests

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
    logger.info("Processing item deletion for %s", file_id)
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    if file.hard_deleted_at is None:
        logger.error("To process an item deletion, it must be hard deleted first.")
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
    data = response.json()

    AiFileJob.objects.create(
        remote_job_id=data["job_id"],
        file=file,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )
    logger.info("Transcription job created for file %s", file_id)


@app.task
def store_transcript_and_call_summary(remote_job_id, url):
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
    AiFileJob.objects.create(
        remote_job_id=summary_response.json()["job_id"],
        file=file,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    )
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
