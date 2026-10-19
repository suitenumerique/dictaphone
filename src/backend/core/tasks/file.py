"""
Tasks related to files.
"""

import json
import logging
from datetime import timedelta
from math import ceil
from urllib.parse import urljoin

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

import requests as requests_lib

from core import analytics
from core.configuration import get_profile_for_email
from core.models import (
    AiFileJob,
    AiJobFailureReasonChoices,
    AiJobStatusChoices,
    AiJobTypeChoices,
    AudioJobModeChoices,
    AudioJobStatusChoices,
    File,
    FileLifecycleStateChoices,
    TranscriptionUsage,
    User,
)
from core.storage import get_storage_bucket_name, get_storage_for_file
from core.tasks.constants import BACKEND_QUEUE
from core.tasks.mail import send_transcription_ready_email
from core.tasks.retry import build_retry_task_options
from core.utils import format_transcript, generate_download_file_url
from core.webhook_models import WhisperXResponse

from dictaphone.celery_app import app

logger = logging.getLogger(__name__)


class DocumentCreationAlreadyInProgress(Exception):
    """Raised when another worker already owns the Docs creation claim."""


class TranscriptionAlreadyPending(ValueError):
    """Raised when a user retries a file with a pending transcript job."""


class PermanentTranscriptionError(RuntimeError):
    """A remote submission error that should not trigger another attempt."""


session = requests_lib.Session()
session.headers.update({"User-Agent": settings.APP_EXTERNAL_USER_AGENT})


@app.task(queue=BACKEND_QUEUE)
@transaction.atomic
def process_file_deletion(file_id):
    """
    Process the deletion of a file.
    Definitely delete it in the database.
    Delete the files from the storage.
    """
    logger.info("Processing file deletion for %s", file_id)
    try:
        file = (
            File.objects.select_for_update().prefetch_related("ai_jobs").get(id=file_id)
        )
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    if file.hard_deleted_at is None:
        logger.error("To process a file deletion, it must be hard deleted first.")
        return

    if _defer_audio_cleanup(file, process_file_deletion):
        return

    storage = get_storage_for_file(file)
    for ai_job in file.ai_jobs.iterator():
        logger.info("Deleting AI job %s for file %s", ai_job.id, file.id)
        # Delete artifacts before committing the cascade, retaining keys if S3 fails.
        storage.delete(ai_job.key)

    logger.info("Deleting file %s", file.file_key)
    storage.delete(file.file_key)
    _delete_audio_and_temporary_objects(file, storage)

    file.delete()


@app.task(queue=BACKEND_QUEUE)
@transaction.atomic
def process_original_file_data_deletion(file_id):
    """Delete only original source file data and keep DB record."""
    logger.info("Processing original file data deletion for %s", file_id)
    try:
        file = File.objects.select_for_update().get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    if file.hard_deleted_at is not None:
        return
    file.lifecycle_state = FileLifecycleStateChoices.PENDING_ORIGINAL_DATA_DELETION
    file.save(update_fields=["lifecycle_state"])
    if _defer_audio_cleanup(file, process_original_file_data_deletion):
        return
    storage = get_storage_for_file(file)
    storage.delete(file.file_key)
    _delete_audio_and_temporary_objects(file, storage)
    file.lifecycle_state = FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
    file.save(update_fields=["lifecycle_state"])


def _defer_audio_cleanup(file, task):
    """Keep keys and tombstones until outstanding signed uploads expire."""
    deadline = file.audio_jobs.aggregate(deadline=Max("expires_at"))["deadline"]
    if deadline and deadline > timezone.now():
        countdown = ceil((deadline - timezone.now()).total_seconds()) + 1
        transaction.on_commit(
            lambda: task.apply_async(args=[file.id], countdown=countdown)
        )
        return True
    return False


def _delete_audio_and_temporary_objects(file, storage):
    """Delete every attempted output, including legacy and incomplete uploads."""
    keys = set(
        file.audio_jobs.exclude(output_key__isnull=True).values_list(
            "output_key", flat=True
        )
    )
    keys.update({file.legacy_audio_file_key, file.temporary_file_key})
    for key in keys:
        storage.delete(key)


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


def _validate_transcription_audio(file, validation):
    """Require an active file and an existing, successfully validated audio output."""
    if file.lifecycle_state != FileLifecycleStateChoices.ACTIVE:
        raise ValueError("Cannot transcribe when file is not in active state")
    extraction_done = (
        validation is not None
        and validation.file_id == file.pk
        and validation.mode == AudioJobModeChoices.VALIDATION
        and validation.status == AudioJobStatusChoices.SUCCESS
        and validation.source_job is not None
        and get_storage_for_file(file).exists(validation.source_job.output_key)
    )
    if not extraction_done:
        raise ValueError("Cannot transcribe without successfully validated audio")


@transaction.atomic
def create_transcription_job(file_id, language=None, *, allow_pending=True):
    """Reserve a transcript job and its input before invoking the submission task."""
    file = File.objects.select_for_update().get(pk=file_id)
    if (
        not allow_pending
        and file.ai_jobs.filter(
            type=AiJobTypeChoices.TRANSCRIPT, status=AiJobStatusChoices.PENDING
        ).exists()
    ):
        raise TranscriptionAlreadyPending(
            "Cannot retry when there is a pending job already."
        )
    validation = file.latest_audio_job
    _validate_transcription_audio(file, validation)
    return AiFileJob.objects.create(
        file=file,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
        language=file.language if language is None else language,
        validated_audio_job=validation,
    )


def _is_retryable_transcription_error(error):
    """Retry transport errors, throttling, timeouts, and server failures."""
    if not isinstance(error, requests_lib.RequestException):
        return False
    if isinstance(error, requests_lib.exceptions.JSONDecodeError):
        return False
    if isinstance(error, requests_lib.HTTPError) and error.response is not None:
        return (
            error.response.status_code in {408, 429}
            or error.response.status_code >= 500
        )
    return True


def _reserve_transcription_audio(ai_job):
    """Charge each submission once, serializing admissions for the same user."""
    if TranscriptionUsage.objects.filter(ai_job_id=ai_job.pk).exists():
        return True

    file = ai_job.file
    # The caller holds the job lock and transaction through the remote call.
    # A user lock also serializes submissions involving different files.
    User.objects.select_for_update(no_key=True).get(pk=file.creator_id)
    now = timezone.now()
    used_seconds = (
        TranscriptionUsage.objects.filter(
            user_id=file.creator_id,
            ignored=False,
            submitted_at__gt=now - timedelta(hours=24),
            submitted_at__lte=now,
        ).aggregate(total=Sum("duration_seconds"))["total"]
        or 0
    )
    duration = file.duration_seconds
    limit_seconds = settings.RATE_LIMIT_AI_TRANSCRIPTION_AUDIO_HOURS_PER_24H * 3600
    if duration is None or duration <= 0:
        ai_job.mark_failed()
        return False
    if used_seconds + duration > limit_seconds:
        ai_job.mark_failed(AiJobFailureReasonChoices.RATE_LIMIT_TRANSCRIPTION_EXCEEDED)
        return False

    TranscriptionUsage.objects.create(
        user_id=file.creator_id,
        ai_job_id=ai_job.pk,
        submitted_at=now,
        duration_seconds=duration,
    )
    return True


# Build retry options separately for each task: Celery mutates the nested
# ``retry_kwargs`` dictionary when it computes a backoff countdown.
@app.task(
    queue=BACKEND_QUEUE,
    **build_retry_task_options(autoretry_for=(requests_lib.RequestException,)),
)
def call_transcribe_service(ai_job_id):
    """Submit a reserved job, preserving its input and identity across retries."""
    error = None
    retryable = False
    with transaction.atomic():
        try:
            ai_job = (
                AiFileJob.objects.select_for_update(of=("self",))
                .select_related("file__creator", "validated_audio_job__source_job")
                .get(pk=ai_job_id, type=AiJobTypeChoices.TRANSCRIPT)
            )
        except AiFileJob.DoesNotExist:
            logger.error("Transcript job %s does not exist", ai_job_id)
            return None

        if (
            ai_job.remote_job_id is not None
            or ai_job.status != AiJobStatusChoices.PENDING
        ):
            return ai_job.id

        file = ai_job.file
        validation = ai_job.validated_audio_job
        try:
            _validate_transcription_audio(file, validation)
            if not _duration_is_allowed(file):
                ai_job.mark_failed(AiJobFailureReasonChoices.AUDIO_TOO_LONG)
                logger.warning(
                    "File duration exceeds maximum allowed for type %s", file.type
                )
                return ai_job.id

            if not _reserve_transcription_audio(ai_job):
                return ai_job.id

            response = session.post(
                settings.AI_SERVICE_URL + "async-jobs/transcribe/",
                json={
                    "user_sub": file.creator.sub,
                    "user_email": file.creator.email,
                    "language": ai_job.language,
                    "cloud_storage_url": generate_download_file_url(
                        file,
                        expires_in=60 * 60 * 24,
                        override_domain=False,
                        key=validation.source_job.output_key,
                    ),
                },
                headers={"Authorization": f"Bearer {settings.AI_SERVICE_API_KEY}"},
                timeout=10,
            )
            response.raise_for_status()
            remote_job_id = response.json()["job_id"]
            if not isinstance(remote_job_id, str) or not remote_job_id:
                raise ValueError("Transcription service returned an invalid job ID")
        except (
            requests_lib.RequestException,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ) as exc:
            error = exc
            retryable = _is_retryable_transcription_error(exc)
            if (
                not retryable
                or call_transcribe_service.request.retries
                >= call_transcribe_service.retry_kwargs["max_retries"]
            ):
                ai_job.mark_failed()
            logger.exception("Submitting transcript job %s failed", ai_job.id)
        else:
            ai_job.remote_job_id = remote_job_id
            ai_job.save(update_fields=["remote_job_id", "updated_at"])
            logger.info("Transcription job submitted for file %s", file.id)

    # Commit terminal failure before raising; autoretry runs outside the job lock.
    if error is not None:
        if isinstance(error, requests_lib.RequestException) and not retryable:
            raise PermanentTranscriptionError(str(error)) from error
        raise error
    return ai_job.id


@app.task(
    queue=BACKEND_QUEUE,
    **build_retry_task_options(autoretry_for=(requests_lib.RequestException,)),
)
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
    ai_transcript_job.failure_reason = ""
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

    profile = get_profile_for_email(file.creator.email)
    if profile.auto_create_in_docs:
        create_document_in_docs.apply_async(args=[ai_transcript_job.id])

    if len(transcript.segments) == 0 and len(transcript.word_segments) == 0:
        logger.info("Transcript is empty, skipping summary")
        if profile.send_notification_email:
            send_transcription_ready_email.apply_async(
                args=[ai_transcript_job.id],
            )
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
        ai_summary_job.mark_failed()
        raise e

    ai_summary_job.remote_job_id = summary_response.json()["job_id"]
    ai_summary_job.save()

    logger.info("Summary job created for file %s", file.id)

    if profile.send_notification_email:
        send_transcription_ready_email.apply_async(
            args=[ai_transcript_job.id],
        )


@app.task(
    queue=BACKEND_QUEUE,
    **build_retry_task_options(autoretry_for=(requests_lib.RequestException,)),
)
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
    ai_summary_job.failure_reason = ""
    ai_summary_job.save()


@app.task(
    queue=BACKEND_QUEUE,
    **build_retry_task_options(autoretry_for=(requests_lib.RequestException,)),
)
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

    claimed = AiFileJob.objects.filter(
        pk=ai_job.pk,
        docs_app_id__isnull=True,
        docs_creation_in_progress=False,
    ).update(docs_creation_in_progress=True)
    if not claimed:
        raise DocumentCreationAlreadyInProgress(
            f"Document creation is already in progress for AI job {ai_job.id}"
        )

    content = ai_job.to_markdown(ai_job.file.creator.language)

    try:
        response = session.post(
            urljoin(settings.DOCS_BASE_URL, "/api/v1.0/documents/create-for-owner/"),
            json={
                "title": ai_job.file.title,
                "content": content,
                "email": ai_job.file.creator.email,
                "sub": ai_job.file.creator.sub,
                "send_notification_email": True,
            },
            headers={
                "Authorization": f"Bearer {settings.DOCS_SERVER_TO_SERVER_API_KEY}",
            },
            timeout=(20, 3 * 60),
        )
        if response.status_code != 201:
            logger.error(
                "Failed to create document in Docs for file %s: %s",
                ai_job.file.id,
                response.text,
            )
            AiFileJob.objects.filter(pk=ai_job.pk).update(
                docs_creation_in_progress=False
            )
            response.raise_for_status()

        docs_app_id = response.json()["id"]
        logger.info(
            "Document created in Docs for file %s => %s (in docs)",
            ai_job.file.id,
            docs_app_id,
        )
        AiFileJob.objects.filter(pk=ai_job.pk).update(
            docs_app_id=docs_app_id,
        )
    except requests_lib.ReadTimeout:
        logger.error(
            "Request to Docs timed out for file %s, "
            "do not considering this a failure to avoid creating multiple files on docs",
            ai_job.file.id,
        )
        # We will "just" lose the link between the job and docs id but that's ok
        return
    except requests_lib.RequestException:
        AiFileJob.objects.filter(pk=ai_job.pk).update(docs_creation_in_progress=False)
        raise
    finally:
        AiFileJob.objects.filter(pk=ai_job.pk).update(
            docs_creation_in_progress=False,
        )
