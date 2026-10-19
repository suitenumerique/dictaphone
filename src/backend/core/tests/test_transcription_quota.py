"""Rolling audio duration quota at the transcription submission boundary."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from threading import Barrier
from unittest.mock import Mock, patch

from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

import pytest
import requests
from freezegun import freeze_time

from core import factories, models
from core.tasks.file import call_transcribe_service, create_transcription_job

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quota_settings(settings):
    """Use a small quota independently of per-file upload restrictions."""
    settings.RATE_LIMIT_AI_TRANSCRIPTION_AUDIO_HOURS_PER_24H = 1
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False


def reserved_job(user=None, duration=1800):
    """Reserve a real validated audio input for submission."""
    file = factories.FileFactory(
        creator=user or factories.UserFactory(),
        duration_seconds=duration,
        upload_bytes=b"audio",
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    return create_transcription_job(file.pk)


@pytest.mark.parametrize(
    "used,allowed", [(0, True), (1800, True), (1801, False), (3600, False)]
)
@patch("core.tasks.file.session.post")
def test_transcription_quota_includes_current_audio(post, used, allowed):
    """Admit the exact limit, rejecting any submission that would exceed it."""
    job = reserved_job()
    factories.AiFileJobFactory(
        file__creator=job.file.creator,
        file__duration_seconds=9999,
        type=models.AiJobTypeChoices.TRANSCRIPT,
        status=models.AiJobStatusChoices.FAILED,
        submitted_at=timezone.now(),
        submitted_audio_duration_seconds=used,
    )
    post.return_value.json.return_value = {"job_id": "quota-transcript"}

    assert call_transcribe_service(job.pk) == job.pk

    assert post.call_count == int(allowed)
    job.refresh_from_db()
    assert job.status == ("pending" if allowed else "failed")
    assert job.failure_reason == (
        "" if allowed else "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"
    )
    assert (job.submitted_at is not None) == allowed
    assert job.submitted_audio_duration_seconds == (1800 if allowed else None)


@pytest.mark.parametrize("age_hours,allowed", [(23.99, False), (24, True), (25, True)])
@patch("core.tasks.file.session.post")
def test_transcription_quota_uses_rolling_submission_time(post, age_hours, allowed):
    """Usage expires at 24 hours, even for jobs created much earlier."""
    job = reserved_job()
    with freeze_time(timezone.now()):
        history = factories.AiFileJobFactory(
            file__creator=job.file.creator,
            type=models.AiJobTypeChoices.TRANSCRIPT,
            submitted_at=timezone.now() - timedelta(hours=age_hours),
            submitted_audio_duration_seconds=3600,
        )
        models.AiFileJob.objects.filter(pk=history.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )
        post.return_value.json.return_value = {"job_id": "quota-transcript"}

        call_transcribe_service(job.pk)

    assert post.call_count == int(allowed)


@patch("core.tasks.file.session.post")
def test_transcription_quota_ignores_other_users_summaries_and_unsubmitted_jobs(post):
    """Only this user's submitted transcript jobs consume the audio allowance."""
    job = reserved_job()
    history = {
        "file__creator": job.file.creator,
        "type": models.AiJobTypeChoices.TRANSCRIPT,
        "submitted_at": timezone.now(),
        "submitted_audio_duration_seconds": 3600,
    }
    factories.AiFileJobFactory(**{**history, "file__creator": factories.UserFactory()})
    factories.AiFileJobFactory(**{**history, "type": models.AiJobTypeChoices.SUMMARIZE})
    factories.AiFileJobFactory(**{**history, "submitted_at": None})
    post.return_value.json.return_value = {"job_id": "quota-transcript"}

    call_transcribe_service(job.pk)

    post.assert_called_once()


@patch("core.tasks.file.session.post")
def test_transcription_quota_automatic_retries_charge_once(post):
    """A transport retry keeps its original charge even at the quota boundary."""
    job = reserved_job(duration=3600)
    success = Mock()
    success.json.return_value = {"job_id": "retried-transcript"}
    post.side_effect = [requests.Timeout("offline"), success]

    result = call_transcribe_service.apply(args=[job.pk], throw=False)

    assert result.successful(), result.result
    assert post.call_count == 2
    job.refresh_from_db()
    assert job.submitted_audio_duration_seconds == 3600
    assert job.failure_reason == ""


@pytest.mark.django_db(transaction=True)
@patch("core.tasks.file.session.post")
def test_concurrent_transcription_quota_admissions_are_per_user(post):
    """Submissions for different files cannot concurrently overspend one quota."""
    user = factories.UserFactory()
    jobs = [reserved_job(user, duration=2400) for _ in range(2)]
    post.return_value.json.return_value = {"job_id": "quota-transcript"}
    barrier = Barrier(2)

    def submit(job):
        try:
            barrier.wait(timeout=10)
            return call_transcribe_service(job.pk)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert set(executor.map(submit, jobs)) == {job.pk for job in jobs}

    post.assert_called_once()
    for job in jobs:
        job.refresh_from_db()
    assert sorted(job.status for job in jobs) == ["failed", "pending"]
    assert [job.failure_reason for job in jobs].count(
        "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"
    ) == 1


@pytest.mark.django_db(transaction=True)
def test_submission_quota_migration_backfills_remote_transcripts():
    """Existing submitted jobs count immediately after the schema is upgraded."""
    remote = factories.AiFileJobFactory(
        type=models.AiJobTypeChoices.TRANSCRIPT,
        status=models.AiJobStatusChoices.FAILED,
        file__duration_seconds=123,
    )
    unsubmitted = factories.AiFileJobFactory(
        type=models.AiJobTypeChoices.TRANSCRIPT, remote_job_id=None
    )
    summary = factories.AiFileJobFactory(type=models.AiJobTypeChoices.SUMMARIZE)
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes("core")
    try:
        executor.migrate([("core", "0020_remove_file_audio_extraction_state")])
        MigrationExecutor(connection).migrate(latest)
        remote.refresh_from_db()
        assert remote.submitted_at == remote.created_at
        assert remote.submitted_audio_duration_seconds == 123
        assert remote.failure_reason == "UNKNOWN_FAILURE"
        for job in (unsubmitted, summary):
            job.refresh_from_db()
            assert job.submitted_at is None
            assert job.submitted_audio_duration_seconds is None
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.parametrize("limit_seconds", [3600, 10770])
def test_failure_backfill_classifies_audio_above_configured_limit(
    settings, limit_seconds
):
    """Only failed jobs strictly above the configured file duration get classified."""
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {"max_duration_seconds": limit_seconds}
    }
    scenarios = [
        ("failed", limit_seconds - 1, "UNKNOWN_FAILURE"),
        ("failed", limit_seconds, "UNKNOWN_FAILURE"),
        ("failed", limit_seconds + 1, "AUDIO_TOO_LONG"),
        ("pending", limit_seconds + 1, ""),
        ("success", limit_seconds + 1, ""),
    ]
    jobs = [
        factories.AiFileJobFactory(
            status=status,
            file__type=models.FileTypeChoices.AUDIO_RECORDING,
            file__duration_seconds=duration,
        )
        for status, duration, _ in scenarios
    ]
    executor = MigrationExecutor(connection)
    historical_apps = executor.loader.project_state(
        executor.loader.graph.leaf_nodes("core")
    ).apps
    migration = import_module("core.migrations.0022_backfill_aifilejob_submissions")

    migration.backfill_submissions(historical_apps, connection.schema_editor())

    for job, (_, _, reason) in zip(jobs, scenarios, strict=True):
        job.refresh_from_db()
        assert job.failure_reason == reason
