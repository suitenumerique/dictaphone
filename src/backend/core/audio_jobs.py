"""Transactional orchestration for the HTTP audio workers."""

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from celery import current_app

from core import analytics
from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AiJobTypeChoices,
    AudioJob,
    AudioJobModeChoices,
    AudioJobStatusChoices,
    File,
    FileLifecycleStateChoices,
    FileUploadStateChoices,
)
from core.storage import (
    get_bucket_configuration_for_file,
    get_storage_bucket_name,
    get_storage_for_file,
)
from core.utils import generate_download_file_url

logger = logging.getLogger(__name__)


class AudioJobConflict(ValueError):
    """An expired, superseded, or unavailable attempt cannot complete."""


def eligible_files():
    """Only uploaded, accessible files can receive media processing work."""
    return File.objects.filter(
        upload_state=FileUploadStateChoices.READY,
        deleted_at__isnull=True,
        hard_deleted_at__isnull=True,
        lifecycle_state=FileLifecycleStateChoices.ACTIVE,
        original_file_data_delete_at__gt=timezone.now(),
        file_auto_hard_delete_at__gt=timezone.now(),
    )


@transaction.atomic
def start_audio_extraction(file_id):
    """Create a new extraction cycle, or reuse work already pending/in progress."""
    file = eligible_files().select_for_update().get(pk=file_id)
    latest = file.latest_audio_job
    if latest and latest.status in {
        AudioJobStatusChoices.PENDING,
        AudioJobStatusChoices.PROCESSING,
    }:
        return latest
    return AudioJob.objects.create(file=file, mode=AudioJobModeChoices.TRANSCODING)


def _retry(job):
    """Preserve a failed attempt and append its successor, under the file lock."""
    if job.attempt_number >= settings.AUDIO_JOB_MAX_RETRIES:
        AiFileJob.objects.filter(
            file_id=job.file_id,
            status=AiJobStatusChoices.PENDING,
            type=AiJobTypeChoices.TRANSCRIPT,
            remote_job_id__isnull=True,
            validated_audio_job__isnull=True,
        ).update(status=AiJobStatusChoices.FAILED)
        return None
    return AudioJob.objects.create(
        file=job.file,
        mode=job.mode,
        extraction_id=job.extraction_id,
        attempt_number=job.attempt_number + 1,
        retry_of=job,
        source_job=job.source_job,
    )


def _expire(job, now):
    """Expire one lease and allocate a fresh attempt, retaining its output key."""
    job.status = AudioJobStatusChoices.STALE
    job.completed_at = now
    job.error = "Worker did not complete before the task deadline."
    job.save(update_fields=["status", "completed_at", "error", "updated_at"])
    _capture_outcome(job, success=False)
    return _retry(job)


@transaction.atomic
def claim_next(mode):
    """Lock the owning file so polling, callbacks, and admin starts serialize."""
    now = timezone.now()
    latest = AudioJob.objects.filter(file_id=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    # Expired attempts in either stage are recovered by either kind of worker.
    # Otherwise exhausted transcoding workers could leave validation permanently stuck.
    files = (
        eligible_files()
        .annotate(current_audio_job=Subquery(latest.values("pk")[:1]))
        .filter(
            audio_jobs__pk=Subquery(latest.values("pk")[:1]),
            audio_jobs__status=AudioJobStatusChoices.PROCESSING,
            audio_jobs__expires_at__lte=now,
        )
        .select_for_update(skip_locked=True, of=("self",))
    )
    for file in files:
        job = file.latest_audio_job
        if job.status == AudioJobStatusChoices.PROCESSING and job.expires_at <= now:
            _expire(job, now)

    latest = AudioJob.objects.filter(file_id=OuterRef("file_id")).order_by(
        "-created_at", "-id"
    )
    candidate = AudioJob.objects.filter(
        file_id__in=eligible_files().values("pk"),
        mode=mode,
        status=AudioJobStatusChoices.PENDING,
        pk=Subquery(latest.values("pk")[:1]),
    ).order_by("created_at", "id")
    for job in candidate:
        file = (
            eligible_files()
            .filter(pk=job.file_id)
            .select_for_update(skip_locked=True)
            .first()
        )
        if file is None:
            continue
        # Re-read after acquiring the file lock; another request may have claimed it.
        job.refresh_from_db()
        if (
            job.status != AudioJobStatusChoices.PENDING
            or file.latest_audio_job.pk != job.pk
        ):
            continue
        job.started_at = now
        job.expires_at = now + timedelta(seconds=settings.AUDIO_JOB_TIMEOUT_SECONDS)
        job.status = AudioJobStatusChoices.PROCESSING
        job.save(update_fields=["started_at", "expires_at", "status", "updated_at"])
        return _worker_payload(job)
    return None


def _worker_payload(job):
    """Sign only the input and the unique output belonging to this attempt."""
    file = job.file
    source_key = (
        file.file_key
        if job.mode == AudioJobModeChoices.TRANSCODING
        else job.source_job.output_key
    )
    payload = {
        "id": str(job.pk),
        "job_kind": job.mode,
        "source_url": generate_download_file_url(
            file,
            key=source_key,
            expires_in=settings.AUDIO_JOB_TIMEOUT_SECONDS,
            override_domain=False,
        ),
    }
    if job.mode == AudioJobModeChoices.TRANSCODING:
        storage = get_storage_for_file(file)
        config = get_bucket_configuration_for_file(file)
        params = {
            "Bucket": get_storage_bucket_name(storage),
            "Key": job.output_key,
            "IfNoneMatch": "*",
        }
        headers = {"If-None-Match": "*"}
        if config.upload_acl:
            params["ACL"] = config.upload_acl
            headers["X-amz-acl"] = config.upload_acl
        payload["destination_url"] = (
            storage.connection.meta.client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=settings.AUDIO_JOB_TIMEOUT_SECONDS,
            )
        )
        payload["destination_headers"] = headers
    return payload


def _queue_transcription(file, validation):
    """Persist the transcription intent once, before scheduling after commit."""
    pending = list(
        AiFileJob.objects.filter(
            file=file,
            type=AiJobTypeChoices.TRANSCRIPT,
            status=AiJobStatusChoices.PENDING,
            remote_job_id__isnull=True,
            validated_audio_job__isnull=True,
        )
    )
    if not pending:
        pending = [
            AiFileJob.objects.create(
                file=file,
                type=AiJobTypeChoices.TRANSCRIPT,
                status=AiJobStatusChoices.PENDING,
                language=file.language,
            )
        ]
    for ai_job in pending:
        ai_job.validated_audio_job = validation
        ai_job.save(update_fields=["validated_audio_job", "updated_at"])
        transaction.on_commit(
            lambda ai_job=ai_job: current_app.tasks[
                "core.tasks.file.call_transcribe_service"
            ].delay(
                file.id,
                ai_job_id=ai_job.id,
                language=ai_job.language,
            )
        )


def _capture_outcome(job, *, success):
    """Retain processing/queue analytics across the two worker stages."""
    attempts = [job.source_job, job] if success else [job]
    properties = {
        "file_id": job.file_id,
        "audio_job_id": job.id,
        "mode": job.mode,
        "input_file_type": job.file.type,
        "preprocessing_time_seconds": sum(
            (attempt.completed_at - attempt.started_at).total_seconds()
            for attempt in attempts
            if attempt.started_at and attempt.completed_at
        ),
        "queue_time_seconds": sum(
            (attempt.started_at - attempt.created_at).total_seconds()
            for attempt in attempts
            if attempt.started_at
        ),
    }
    event = (
        analytics.EventName.AUDIO_EXTRACTION_SUCCESS
        if success
        else analytics.EventName.AUDIO_EXTRACTION_FAILURE
    )
    if success:
        properties["audio_duration_seconds"] = job.source_job.duration_seconds
    else:
        properties.update(
            {
                "error_type": "AudioJobTimeout"
                if job.status == AudioJobStatusChoices.STALE
                else "AudioWorkerFailure",
                "error_message": job.error,
                "retryable": job.attempt_number < settings.AUDIO_JOB_MAX_RETRIES,
            }
        )
    transaction.on_commit(
        lambda: analytics.capture_event(
            event, user=job.file.creator, properties=properties
        )
    )


@transaction.atomic
def complete_job(mode, data):
    """Complete the current lease once and append the next stage or retry."""
    job = AudioJob.objects.select_related("source_job", "file").get(
        pk=data["id"], mode=mode
    )
    file = File.objects.select_for_update().get(pk=job.file_id)
    job.refresh_from_db()
    if job.status in {AudioJobStatusChoices.SUCCESS, AudioJobStatusChoices.FAILED}:
        # Retransmission is harmless only when its outcome agrees with the stored result.
        expected = (
            AudioJobStatusChoices.SUCCESS
            if data["status"] == "success"
            else AudioJobStatusChoices.FAILED
        )
        if job.status == expected:
            return
        raise AudioJobConflict(
            "Attempt has already completed with a different outcome."
        )
    now = timezone.now()
    if (
        job.status != AudioJobStatusChoices.PROCESSING
        or file.latest_audio_job.pk != job.pk
    ):
        raise AudioJobConflict("Attempt is no longer current or was not claimed.")
    if job.expires_at <= now:
        # The next poll recovers the expired lease; reject late success here.
        raise AudioJobConflict("Attempt has expired.")
    if not eligible_files().filter(pk=file.pk).exists():
        raise AudioJobConflict("File is no longer available for audio processing.")
    if data["status"] == "success" and mode == AudioJobModeChoices.TRANSCODING:
        if not get_storage_for_file(file).exists(job.output_key):
            raise AudioJobConflict("Transcoding output has not been uploaded.")
    job.status = (
        AudioJobStatusChoices.SUCCESS
        if data["status"] == "success"
        else AudioJobStatusChoices.FAILED
    )
    job.completed_at = now
    job.error = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1", data.get("error") or "")
    job.metadata = data.get("metadata") or {}
    job.duration_seconds = data.get("duration_seconds")
    job.save(
        update_fields=[
            "status",
            "completed_at",
            "error",
            "metadata",
            "duration_seconds",
            "updated_at",
        ]
    )
    if job.status == AudioJobStatusChoices.FAILED:
        _capture_outcome(job, success=False)
        _retry(job)
        return
    if mode == AudioJobModeChoices.TRANSCODING:
        AudioJob.objects.create(
            file=file,
            mode=AudioJobModeChoices.VALIDATION,
            source_job=job,
            extraction_id=job.extraction_id,
        )
        return
    duration = job.source_job.duration_seconds
    if (
        file.duration_seconds > 0
        and abs(duration - file.duration_seconds) / file.duration_seconds > 0.15
    ):
        logger.warning(
            "Suspicious audio duration difference for file %s: input=%s, extracted=%s seconds",
            file.id,
            file.duration_seconds,
            duration,
        )
    file.duration_seconds = duration
    file.save(update_fields=["duration_seconds", "updated_at"])
    _queue_transcription(file, job)
    _capture_outcome(job, success=True)
