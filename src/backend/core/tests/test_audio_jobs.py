"""Attempt history, worker API, concurrency, migration, and storage cleanup."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.core.management import call_command
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

import pytest
import requests
from rest_framework.test import APIClient

from core import factories, models
from core.audio_jobs import start_audio_extraction
from core.storage import get_storage_for_file
from core.tasks.file import (
    call_transcribe_service,
    process_file_deletion,
    process_original_file_data_deletion,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def worker_settings(settings):
    """Each worker has a distinct token; leases and retries are deterministic."""
    settings.AUDIO_EXTRACTOR_TRANSCODING_TOKEN = (
        "test-transcoding-token-at-least-32-chars"
    )
    settings.AUDIO_EXTRACTOR_VALIDATION_TOKEN = (
        "test-validation-token-at-least-32-chars"
    )
    settings.AUDIO_JOB_TIMEOUT_SECONDS = 120
    settings.AUDIO_JOB_MAX_RETRIES = 3


def worker(mode="transcoding"):
    """Authenticate a worker without a user session."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer test-{mode}-token-at-least-32-chars")
    return client


def ready_file(**kwargs):
    """Build an uploaded file eligible for processing."""
    return factories.FileFactory(
        upload_bytes=b"source",
        update_upload_state=models.FileUploadStateChoices.READY,
        **kwargs,
    )


def poll(mode="transcoding"):
    """Poll one queue through its token-authenticated endpoint."""
    return worker(mode).get(f"/audio-jobs/{mode}/next")


def complete(job, outcome="success", **kwargs):
    """Report a completion through the actual worker API."""
    return worker(job.mode).post(
        f"/audio-jobs/{job.mode}/complete",
        {"id": str(job.id), "status": outcome, **kwargs},
        format="json",
    )


def finish_transcoding(file):
    """Upload an attempt's output and report it to schedule validation."""
    assert poll().status_code == 200
    job = file.latest_audio_job
    get_storage_for_file(file).save(job.output_key, BytesIO(b"audio"))
    assert complete(job, duration_seconds=12.5).status_code == 200
    return job


@pytest.mark.parametrize("mode", ["transcoding", "validation"])
def test_worker_auth_requires_matching_bearer_token(mode, settings):
    """User sessions, raw tokens, other modes, and empty secrets cannot authenticate."""
    client = APIClient()
    url = f"/audio-jobs/{mode}/next"
    assert client.get(url).status_code == 401
    client.force_login(factories.UserFactory())
    assert client.get(url).status_code == 401
    other = "validation" if mode == "transcoding" else "transcoding"
    assert worker(other).get(url).status_code == 401
    client.credentials(HTTP_AUTHORIZATION=f"test-{mode}-token-at-least-32-chars")
    assert client.get(url).status_code == 401
    setattr(settings, f"AUDIO_EXTRACTOR_{mode.upper()}_TOKEN", "")
    assert worker(mode).get(url).status_code == 401


def test_poll_claims_once_and_signed_urls_match_lease(settings):
    """The API contract signs this attempt's input and unique destination."""
    file = ready_file()
    job = start_audio_extraction(file.id)
    assert job.started_at is None
    response = poll()
    assert response.status_code == 200
    assert set(response.data) == {
        "id",
        "job_kind",
        "source_url",
        "destination_url",
        "destination_headers",
    }
    assert response.data["id"] == str(job.id)
    assert response.data["job_kind"] == "transcoding"
    for name in ("source_url", "destination_url"):
        assert parse_qs(urlsplit(response.data[name]).query)["X-Amz-Expires"] == ["120"]
    assert file.file_key in response.data["source_url"]
    assert job.output_key in response.data["destination_url"]
    job.refresh_from_db()
    assert job.created_at <= job.started_at
    assert job.expires_at - job.started_at == timedelta(
        seconds=settings.AUDIO_JOB_TIMEOUT_SECONDS
    )
    assert poll().status_code == 204
    assert poll("validation").status_code == 204


def test_signed_worker_urls_can_download_and_upload():
    """The issued URLs work with the extractor's GET and PUT contract."""
    file = ready_file()
    start_audio_extraction(file.id)
    data = poll().data
    source = requests.get(data["source_url"], timeout=10)
    assert source.status_code == 200
    assert source.content == b"source"
    uploaded = requests.put(
        data["destination_url"],
        data=b"derived",
        headers=data["destination_headers"],
        timeout=10,
    )
    assert uploaded.status_code == 200
    overwrite = requests.put(
        data["destination_url"],
        data=b"replacement",
        headers=data["destination_headers"],
        timeout=10,
    )
    assert overwrite.status_code == 412
    job = file.latest_audio_job
    assert complete(job, duration_seconds=10).status_code == 200


def test_validation_schedules_transcription_once(
    django_capture_on_commit_callbacks, caplog
):
    """Only independent validation success publishes duration and a transcription intent."""
    file = ready_file(duration_seconds=999)
    start_audio_extraction(file.id)
    with (
        patch("core.tasks.file.call_transcribe_service.delay") as transcribe,
        patch("core.audio_jobs.analytics.capture_event") as capture,
    ):
        transcoding = finish_transcoding(file)
        transcribe.assert_not_called()
        file.refresh_from_db()
        assert file.duration_seconds == 999
        response = poll("validation")
        assert response.status_code == 200
        assert set(response.data) == {"id", "job_kind", "source_url"}
        assert transcoding.output_key in response.data["source_url"]
        validation = file.latest_audio_job
        with django_capture_on_commit_callbacks(execute=True):
            assert complete(validation).status_code == 200
            assert complete(validation).status_code == 200
        transcribe.assert_called_once()
        capture.assert_called_once()
        assert capture.call_args.kwargs["properties"]["audio_duration_seconds"] == 12.5
        assert capture.call_args.kwargs["properties"]["preprocessing_time_seconds"] >= 0
    file.refresh_from_db()
    assert file.duration_seconds == 12.5
    assert (
        file.audio_extraction_state
        == models.FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    assert file.ai_jobs.get().validated_audio_job_id == validation.id
    assert validation.source_job_id == transcoding.id
    assert "Suspicious audio duration difference" in caplog.text
    client = APIClient()
    client.force_login(file.creator)
    assert (
        client.get(f"/api/v1.0/files/{file.id}/").data["audio_extraction_state"]
        == "extraction_done"
    )


@pytest.mark.parametrize("mode", ["transcoding", "validation"])
def test_failure_retry_limit_preserves_all_attempts(mode):
    """Each stage has three retries and failures never overwrite previous rows/keys."""
    file = ready_file()
    initial = start_audio_extraction(file.id)
    if mode == "validation":
        finish_transcoding(file)
        initial = file.latest_audio_job
    for attempt in range(4):
        assert poll(mode).status_code == 200
        job = file.latest_audio_job
        assert job.attempt_number == attempt
        assert (
            complete(
                job,
                "failure",
                error="cannot process",
                metadata={"download_seconds": 1.2},
            ).status_code
            == 200
        )
        job.refresh_from_db()
        assert job.status == models.AudioJobStatusChoices.FAILED
        assert job.completed_at is not None
        assert complete(job, "failure", error="cannot process").status_code == 200
    assert poll(mode).status_code == 204
    jobs = list(file.audio_jobs.filter(mode=mode))
    assert len(jobs) == 4
    assert jobs[0].id == initial.id
    assert [job.attempt_number for job in jobs] == [0, 1, 2, 3]
    assert [job.retry_of_id for job in jobs[1:]] == [job.id for job in jobs[:-1]]
    if mode == "transcoding":
        assert len({job.output_key for job in jobs}) == 4
    else:
        assert len({job.source_job_id for job in jobs}) == 1
    assert file.audio_extraction_state == "audio_extraction_failed"


def test_failure_analytics_and_zero_retry_configuration(
    settings, django_capture_on_commit_callbacks
):
    """No retries means one terminal attempt, with sanitized failure analytics."""
    settings.AUDIO_JOB_MAX_RETRIES = 0
    file = ready_file()
    job = start_audio_extraction(file.pk)
    intent = factories.AiFileJobFactory(
        file=file, type="transcript", status="pending", remote_job_id=None
    )
    poll()
    with patch("core.audio_jobs.analytics.capture_event") as capture:
        with django_capture_on_commit_callbacks(execute=True):
            assert (
                complete(
                    job,
                    "failure",
                    error="Failed https://storage.test/audio?signature=secret",
                ).status_code
                == 200
            )
        assert capture.call_args.kwargs["properties"]["retryable"] is False
        assert (
            "signature=secret"
            not in capture.call_args.kwargs["properties"]["error_message"]
        )
    intent.refresh_from_db()
    assert intent.status == "failed"
    assert file.audio_jobs.count() == 1
    assert poll().status_code == 204


def test_stale_attempt_replaced_and_late_completion_rejected(settings):
    """A previous lease cannot publish duration or validate another attempt's output."""
    file = ready_file()
    start_audio_extraction(file.id)
    poll()
    old = file.latest_audio_job
    expired = timezone.now() - timedelta(seconds=1)
    models.AudioJob.objects.filter(pk=old.pk).update(expires_at=expired)
    assert complete(old, duration_seconds=12).status_code == 409
    assert poll().status_code == 200
    old.refresh_from_db()
    retry = file.latest_audio_job
    assert old.status == models.AudioJobStatusChoices.STALE
    assert retry.retry_of_id == old.id
    assert retry.output_key != old.output_key
    assert complete(old, "failure", error="late").status_code == 409
    models.AudioJob.objects.filter(pk=retry.pk).update(expires_at=expired)
    settings.AUDIO_JOB_MAX_RETRIES = 1
    assert poll().status_code == 204
    assert file.audio_extraction_state == "audio_extraction_failed"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "success"},
        {"status": "success", "duration_seconds": 0},
        {"status": "success", "duration_seconds": -1},
        {"status": "success", "duration_seconds": "NaN"},
        {"status": "failure"},
        {"status": "failure", "error": "bad", "duration_seconds": 2},
        {"status": "success", "duration_seconds": 2, "error": "bad"},
        {
            "status": "failure",
            "error": "bad",
            "metadata": {"download_seconds": "Infinity"},
        },
    ],
)
def test_invalid_completion_does_not_change_attempt(payload):
    """Malformed results leave the claimed attempt unchanged."""
    file = ready_file()
    job = start_audio_extraction(file.id)
    poll()
    response = worker().post(
        "/audio-jobs/transcoding/complete",
        {"id": str(job.id), **payload},
        format="json",
    )
    assert response.status_code == 400
    job.refresh_from_db()
    assert job.status == models.AudioJobStatusChoices.PROCESSING
    assert file.audio_jobs.count() == 1


def test_completion_requires_claim_output_and_correct_mode():
    """Unclaimed work, missing objects, and mode mismatches cannot advance."""
    file = ready_file()
    job = start_audio_extraction(file.id)
    assert complete(job, duration_seconds=2).status_code == 409
    poll()
    assert complete(job, duration_seconds=2).status_code == 409
    response = worker("validation").post(
        "/audio-jobs/validation/complete",
        {"id": str(job.id), "status": "success"},
        format="json",
    )
    assert response.status_code == 404
    assert file.audio_jobs.count() == 1


@pytest.mark.parametrize("change", ["soft_delete", "hard_delete", "retention"])
def test_unavailable_files_cannot_claim_or_complete(change):
    """Deletion and retention prevent further audio processing."""
    file = ready_file()
    start_audio_extraction(file.id)
    poll()
    job = file.latest_audio_job
    if change == "soft_delete":
        file.soft_delete()
    elif change == "hard_delete":
        file.soft_delete()
        file.hard_delete()
    else:
        models.File.objects.filter(pk=file.pk).update(
            original_file_data_delete_at=timezone.now()
        )
    assert complete(job, "failure", error="unavailable").status_code == 409
    assert poll().status_code == 204


@pytest.mark.django_db(transaction=True)
def test_concurrent_polls_claim_single_attempt():
    """Independent DB connections race through the actual HTTP endpoint."""
    file = ready_file()
    start_audio_extraction(file.id)

    def request_job(_):
        try:
            return poll().status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(request_job, range(2))) == [200, 204]
    assert file.audio_jobs.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_validation_completions_schedule_one_transcription():
    """Two callback requests serialize and publish one transcription intent."""
    file = ready_file()
    start_audio_extraction(file.pk)
    finish_transcoding(file)
    poll("validation")
    job = file.latest_audio_job

    def report(_):
        try:
            return complete(job).status_code
        finally:
            connections.close_all()

    with patch("core.tasks.file.call_transcribe_service.delay") as transcribe:
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(report, range(2))) == [200, 200]
        transcribe.assert_called_once()
    assert file.ai_jobs.count() == 1


def test_linked_transcription_uses_its_validated_output_after_new_extraction():
    """An admin restart cannot replace the audio attached to an existing AI intent."""
    file = ready_file(
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    validation = file.latest_audio_job
    job = factories.AiFileJobFactory(
        file=file,
        type=models.AiJobTypeChoices.TRANSCRIPT,
        status=models.AiJobStatusChoices.PENDING,
        remote_job_id=None,
        validated_audio_job=validation,
    )
    start_audio_extraction(file.pk)
    models.AudioJob.objects.filter(pk=file.latest_audio_job.pk).update(status="failed")
    response = SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"job_id": "stable-audio-result"}
    )
    with patch("core.tasks.file.session.post", return_value=response) as post:
        call_transcribe_service(file.pk, ai_job_id=job.pk)
    assert (
        validation.source_job.output_key
        in post.call_args.kwargs["json"]["cloud_storage_url"]
    )


def test_admin_restart_preserves_already_validated_transcription_intents(
    django_capture_on_commit_callbacks,
):
    """A new validation creates its own intent rather than rebinding queued older work."""
    file = ready_file(
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    previous_validation = file.latest_audio_job
    previous_intent = factories.AiFileJobFactory(
        file=file,
        type=models.AiJobTypeChoices.TRANSCRIPT,
        status=models.AiJobStatusChoices.PENDING,
        remote_job_id=None,
        validated_audio_job=previous_validation,
    )
    start_audio_extraction(file.pk)
    finish_transcoding(file)
    poll("validation")
    with patch("core.tasks.file.call_transcribe_service.delay") as transcribe:
        with django_capture_on_commit_callbacks(execute=True):
            assert complete(file.latest_audio_job).status_code == 200
        transcribe.assert_called_once()
    previous_intent.refresh_from_db()
    assert previous_intent.validated_audio_job_id == previous_validation.id
    assert file.ai_jobs.count() == 2


@pytest.mark.parametrize(
    "state,expected",
    [
        (None, "pending_audio_extraction"),
        (models.FileAudioExtractionStateChoices.EXTRACTING_AUDIO, "extracting_audio"),
        (models.FileAudioExtractionStateChoices.EXTRACTION_DONE, "extraction_done"),
        (
            models.FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED,
            "audio_extraction_failed",
        ),
    ],
)
def test_api_and_queryset_state_resolvers_agree(state, expected):
    """Python and SQL expose the same public extraction states."""
    file = factories.FileFactory(audio_extraction_state=state)
    assert file.audio_extraction_state == expected
    assert (
        models.File.objects.with_audio_state().get(pk=file.pk).audio_extraction_state
        == expected
    )


@pytest.mark.parametrize(
    "command",
    [
        "purge_deleted_files",
        "clean_pending_files",
        "auto_hard_delete_files",
        "delete_original_files_data",
    ],
)
@pytest.mark.django_db(transaction=True)
def test_cleanup_commands_delete_all_attempt_outputs_and_temporary_key(command):
    """Retried, stale, successful, and legacy outputs are all removed by lifecycle cleanup."""
    file = factories.FileFactory(upload_bytes=b"source")
    storage = get_storage_for_file(file)
    keys = {file.file_key, file.temporary_file_key, file.legacy_audio_file_key}
    for outcome in models.AudioJobStatusChoices.values:
        job = models.AudioJob.objects.create(
            file=file, mode="transcoding", status=outcome
        )
        keys.add(job.output_key)
    for key in keys - {file.file_key}:
        storage.save(key, BytesIO(b"artifact"))
    old = timezone.now() - timedelta(days=500)
    models.File.objects.filter(pk=file.pk).update(
        created_at=old,
        original_file_data_delete_at=old,
        original_file_data_delete_at_with_grace_period=old,
        file_auto_hard_delete_at=old,
        file_auto_hard_delete_at_with_grace_period=old,
    )
    if command == "purge_deleted_files":
        file.soft_delete()
        file.hard_delete()
    call_command(command)
    assert all(not storage.exists(key) for key in keys)
    if command == "delete_original_files_data":
        file.refresh_from_db()
        assert (
            file.lifecycle_state
            == models.FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
        )
    else:
        assert not models.File.objects.filter(pk=file.pk).exists()


@pytest.mark.parametrize(
    "task", [process_file_deletion, process_original_file_data_deletion]
)
def test_cleanup_preserves_keys_until_signed_upload_expires(
    task, django_capture_on_commit_callbacks
):
    """Even completed workers may retain a valid PUT URL; cleanup keeps their keys."""
    file = ready_file()
    job = start_audio_extraction(file.id)
    poll()
    if task is process_file_deletion:
        file.soft_delete()
        file.hard_delete()
    with patch.object(task, "apply_async") as reschedule:
        with django_capture_on_commit_callbacks(execute=True):
            task(file.id)
        reschedule.assert_called_once()
    assert models.File.objects.filter(pk=file.pk).exists()
    storage = get_storage_for_file(file)
    storage.save(job.output_key, BytesIO(b"late upload"))
    models.AudioJob.objects.filter(pk=job.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    task(file.id)
    assert not storage.exists(job.output_key)


@pytest.mark.django_db(transaction=True)
def test_migration_preserves_all_states_and_legacy_keys_without_storage_operations():
    """Backfill uses historical models, preserves files, and does not trigger transcription."""
    files = [factories.FileFactory() for _ in range(4)]
    states = models.FileAudioExtractionStateChoices.values
    executor = MigrationExecutor(connection)
    old_target = [("core", "0017_aifilejob_docs_creation_in_progress")]
    target = [("core", "0018_audio_jobs")]
    try:
        executor.migrate(old_target)
        old_file = executor.loader.project_state(old_target).apps.get_model(
            "core", "File"
        )
        for file, state in zip(files, states, strict=True):
            old_file.objects.filter(pk=file.pk).update(audio_extraction_state=state)
        with (
            patch("core.storage.get_storage_for_file") as storage,
            patch("core.tasks.file.call_transcribe_service.delay") as transcribe,
        ):
            MigrationExecutor(connection).migrate(target)
            storage.assert_not_called()
            transcribe.assert_not_called()
        for file, state in zip(files, states, strict=True):
            file.refresh_from_db()
            expected = (
                "pending_audio_extraction" if state == "extracting_audio" else state
            )
            assert file.audio_extraction_state == expected
            if state == "extraction_done":
                assert file.audio_file_key == file.legacy_audio_file_key
                assert file.audio_jobs.count() == 2
            else:
                assert file.audio_jobs.count() == 1
        assert all(job.started_at is None for job in models.AudioJob.objects.all())
    finally:
        MigrationExecutor(connection).migrate(target)
