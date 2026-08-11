"""
Tasks related to files.
"""

import json
import logging
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone

import requests as requests_lib

from core import analytics
from core.audio import (
    AudioExtractionError,
    AudioExtractionRetryableError,
    extract_audio_to_storage,
)
from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AiJobTypeChoices,
    File,
    FileAudioExtractionStateChoices,
    FileLifecycleStateChoices,
)
from core.storage import get_storage_bucket_name, get_storage_for_file
from core.tasks.retry import build_retry_task_options
from core.utils import format_transcript, generate_download_file_url
from core.webhook_models import WhisperXResponse

from dictaphone.celery_app import app

logger = logging.getLogger(__name__)


session = requests_lib.Session()
session.headers.update({"User-Agent": settings.APP_EXTERNAL_USER_AGENT})

AUDIO_EXTRACTION_QUEUE = "dictaphone-audio"


@app.task
def process_file_deletion(file_id):
    """
    Process the deletion of a file.
    Definitely delete it in the database.
    Delete the files from the storage.
    """
    logger.info("Processing file deletion for %s", file_id)
    try:
        file = File.objects.prefetch_related("ai_jobs").get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    if file.hard_deleted_at is None:
        logger.error("To process a file deletion, it must be hard deleted first.")
        return

    for ai_job in file.ai_jobs.iterator():
        logger.info("Deleting AI job %s for file %s", ai_job.id, file.id)
        ai_job.delete()

    logger.info("Deleting file %s", file.file_key)
    storage = get_storage_for_file(file)
    storage.delete(file.file_key)
    storage.delete(file.audio_file_key)

    file.delete()


@app.task
def process_original_file_data_deletion(file_id):
    """Delete only original source file data and keep DB record."""
    logger.info("Processing original file data deletion for %s", file_id)
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    storage = get_storage_for_file(file)
    storage.delete(file.file_key)
    storage.delete(file.audio_file_key)
    file.lifecycle_state = FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
    file.save(update_fields=["lifecycle_state"])


# Build retry options separately for each task: Celery mutates the nested
# ``retry_kwargs`` dictionary when it computes a backoff countdown.
def _mark_transcription_job_failed(ai_job_id):
    """Mark a pending transcription job failed when preparation cannot complete."""
    if ai_job_id is not None:
        AiFileJob.objects.filter(
            id=ai_job_id, status=AiJobStatusChoices.PENDING
        ).update(status=AiJobStatusChoices.FAILED)


def _delete_extracted_audio(  # pylint: disable=broad-exception-caught
    file,
):
    """Remove an extracted object without hiding the original task failure."""
    try:
        get_storage_for_file(file).delete(file.audio_file_key)
    except Exception:  # noqa: BLE001 - cleanup must not mask the root cause
        logger.warning("Could not clean extracted audio for file %s", file.id)


def _queue_transcription(file_id, *, ai_job_id=None, language=None):
    """Queue transcription with or without an already-created AI job."""
    if ai_job_id is None:
        call_transcribe_service.delay(file_id)
    else:
        call_transcribe_service.delay(file_id, language=language, ai_job_id=ai_job_id)
    return ai_job_id


def _queue_transcription_if_ready(file, *, ai_job_id=None, language=None):
    """Queue transcription when extraction is complete, returning handled/result."""
    if (
        file.audio_extraction_state
        == FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
    ):
        _mark_transcription_job_failed(ai_job_id)
        return True, None

    if file.audio_extraction_state != FileAudioExtractionStateChoices.EXTRACTION_DONE:
        return False, None

    if not get_storage_for_file(file).exists(file.audio_file_key):
        return False, None

    return True, _queue_transcription(
        file.id,
        ai_job_id=ai_job_id,
        language=language,
    )


@app.task(**build_retry_task_options(autoretry_for=(AudioExtractionRetryableError,)))
def extract_audio(file_id, ai_job_id=None, language=None):
    """Validate, convert, and store a file's audio representation."""
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        _mark_transcription_job_failed(ai_job_id)
        return None

    handled, result = _queue_transcription_if_ready(
        file,
        ai_job_id=ai_job_id,
        language=language,
    )
    if handled:
        return result

    if file.audio_extraction_state == FileAudioExtractionStateChoices.EXTRACTION_DONE:
        File.objects.filter(pk=file.pk).update(
            audio_extraction_state=FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
        )
        file.audio_extraction_state = (
            FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
        )

    if (
        file.audio_extraction_state
        != FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
    ):
        return None

    claimed = File.objects.filter(
        pk=file.pk,
        audio_extraction_state=FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION,
    ).update(audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTING_AUDIO)
    if claimed != 1:
        file.refresh_from_db()
        handled, result = _queue_transcription_if_ready(
            file,
            ai_job_id=ai_job_id,
            language=language,
        )
        return result if handled else None

    try:
        duration_seconds = extract_audio_to_storage(file)
    except AudioExtractionRetryableError:
        logger.warning(
            "Transient audio extraction failure for file %s; retrying",
            file.id,
            exc_info=True,
        )
        File.objects.filter(pk=file.pk).update(
            audio_extraction_state=FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
        )
        raise
    except AudioExtractionError:
        logger.exception("Audio extraction failed for file %s", file.id)
        _delete_extracted_audio(file)
        File.objects.filter(pk=file.pk).update(
            audio_extraction_state=FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
        )
        _mark_transcription_job_failed(ai_job_id)
        raise
    except Exception:
        logger.exception("Unexpected audio extraction failure for file %s", file.id)
        _delete_extracted_audio(file)
        File.objects.filter(pk=file.pk).update(
            audio_extraction_state=FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
        )
        _mark_transcription_job_failed(ai_job_id)
        raise

    File.objects.filter(pk=file.pk).update(
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
        duration_seconds=duration_seconds,
    )

    return _queue_transcription(
        file_id,
        ai_job_id=ai_job_id,
        language=language,
    )


def queue_audio_extraction(file_id, *, ai_job_id=None, language=None):
    """Queue extraction on the worker reserved for media processing."""
    extract_audio.apply_async(
        args=[file_id],
        kwargs={"ai_job_id": ai_job_id, "language": language},
        queue=AUDIO_EXTRACTION_QUEUE,
    )


def _duration_is_allowed(file):
    """Return whether the validated or declared duration meets upload restrictions."""
    if not settings.FILE_UPLOAD_APPLY_RESTRICTIONS:
        return True

    max_duration_seconds = settings.FILE_UPLOAD_RESTRICTIONS[file.type][
        "max_duration_seconds"
    ]
    return (
        file.duration_seconds is not None
        and file.duration_seconds <= max_duration_seconds
    )


@app.task(**build_retry_task_options(autoretry_for=(requests_lib.RequestException,)))
def call_transcribe_service(file_id, language=None, ai_job_id=None):
    """
    Call the transcribe service for a given file.

    If language is not provided, it will use the file's language.
    """
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return None

    if file.lifecycle_state != FileLifecycleStateChoices.ACTIVE:
        raise ValueError("Cannot transcribe when file is not in active state")

    if (
        file.audio_extraction_state
        == FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
    ):
        _mark_transcription_job_failed(ai_job_id)
        raise ValueError("Cannot transcribe when audio extraction has failed")

    if language is None:
        language = file.language

    if ai_job_id is None:
        ai_transcribe_job = AiFileJob.objects.create(
            remote_job_id=None,
            file=file,
            type=AiJobTypeChoices.TRANSCRIPT,
            status=AiJobStatusChoices.PENDING,
            language=language,
        )
    else:
        ai_transcribe_job = AiFileJob.objects.get(
            id=ai_job_id, type=AiJobTypeChoices.TRANSCRIPT
        )

    extraction_done = (
        file.audio_extraction_state == FileAudioExtractionStateChoices.EXTRACTION_DONE
        and get_storage_for_file(file).exists(file.audio_file_key)
    )
    if not extraction_done:
        if (
            file.audio_extraction_state
            == FileAudioExtractionStateChoices.EXTRACTING_AUDIO
        ):
            File.objects.filter(pk=file.pk).update(
                audio_extraction_state=FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
            )
        queue_audio_extraction(
            file.id,
            ai_job_id=ai_transcribe_job.id,
            language=language,
        )
        return ai_transcribe_job.id

    if not _duration_is_allowed(file):
        ai_transcribe_job.status = AiJobStatusChoices.FAILED
        logger.warning("File duration exceeds maximum allowed for type %s", file.type)
        ai_transcribe_job.save(update_fields=["status"])
        return ai_transcribe_job.id

    try:
        response = session.post(
            settings.AI_SERVICE_URL + "async-jobs/transcribe/",
            json={
                "user_sub": file.creator.sub,
                "user_email": file.creator.email,
                "language": language,
                "cloud_storage_url": generate_download_file_url(
                    file,
                    expires_in=60 * 60 * 24,
                    override_domain=False,
                    key=file.audio_file_key,
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
    return ai_transcribe_job.id


@app.task(**build_retry_task_options(autoretry_for=(requests_lib.RequestException,)))
def handle_transcript_received(remote_job_id, url: str | None):
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
    if url is None:
        content = json.dumps({"segments": [], "word_segments": []}).encode("utf-8")
    else:
        # could be streamed to S3 later
        response = session.get(url, timeout=(10, 20))
        response.raise_for_status()
        content = response.content

    transcript = WhisperXResponse(**json.loads(content))

    storage = get_storage_for_file(file)
    bucket_name = get_storage_bucket_name(storage)
    s3_client = storage.connection.meta.client
    s3_client.put_object(
        Bucket=bucket_name,
        Key=ai_transcript_job.key,
        Body=content,
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
            "language": ai_transcript_job.language,
            "file_id": ai_transcript_job.file.id,
            "transcript_size": len(content),
            "file_duration_seconds": ai_transcript_job.file.duration_seconds,
        },
    )

    create_document_in_docs.apply_async(args=[ai_transcript_job.id])

    if len(transcript.segments) == 0 and len(transcript.word_segments) == 0:
        logger.info("Transcript is empty, skipping summary")
        return

    ai_summary_job = AiFileJob.objects.create(
        remote_job_id=None,
        file=file,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
        language=ai_transcript_job.language,
    )

    try:
        summary_response = session.post(
            settings.AI_SERVICE_URL + "async-jobs/summarize/",
            json={
                "user_sub": file.creator.sub,
                "user_email": file.creator.email,
                "language": ai_transcript_job.language,
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


@app.task(**build_retry_task_options(autoretry_for=(requests_lib.RequestException,)))
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
    response = session.get(url, timeout=(10, 20))
    response.raise_for_status()

    storage = get_storage_for_file(file)
    bucket_name = get_storage_bucket_name(storage)
    s3_client = storage.connection.meta.client
    s3_client.put_object(
        Bucket=bucket_name,
        Key=ai_summary_job.key,
        Body=response.content,
        ContentType="text/plain",
    )
    logger.info("Summary stored for file %s & url %s", file.id, url)
    ai_summary_job.status = AiJobStatusChoices.SUCCESS
    ai_summary_job.save()


@app.task(**build_retry_task_options(autoretry_for=(requests_lib.RequestException,)))
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

    try:
        response = session.post(
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
            timeout=(20, 3 * 60),
        )
    except requests_lib.ReadTimeout:
        logger.error(
            "Request to Docs timed out for file %s, "
            "do not considering this a failure to avoid creating multiple files on docs",
            ai_job.file.id,
        )
        # We will "just" loose the link between the job and docs id but that's ok
        return

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
