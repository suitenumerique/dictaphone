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
from rest_framework.test import APIClient

from core import factories, models
from core.tasks.file import (
    call_transcribe_service,
    create_transcription_job,
    process_file_deletion,
)

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
    factories.TranscriptionUsageFactory(
        user=job.file.creator,
        submitted_at=timezone.now(),
        duration_seconds=used,
    )
    post.return_value.json.return_value = {"job_id": "quota-transcript"}

    assert call_transcribe_service(job.pk) == job.pk

    assert post.call_count == int(allowed)
    job.refresh_from_db()
    assert job.status == ("pending" if allowed else "failed")
    assert job.failure_reason == (
        "" if allowed else "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"
    )
    assert (
        models.TranscriptionUsage.objects.filter(ai_job_id=job.pk).exists() == allowed
    )
    if allowed:
        assert (
            models.TranscriptionUsage.objects.get(ai_job_id=job.pk).duration_seconds
            == 1800
        )


@pytest.mark.parametrize("age_hours,allowed", [(23.99, False), (24, True), (25, True)])
@patch("core.tasks.file.session.post")
def test_transcription_quota_uses_rolling_submission_time(post, age_hours, allowed):
    """Usage expires at 24 hours, even for jobs created much earlier."""
    job = reserved_job()
    with freeze_time(timezone.now()):
        history = factories.TranscriptionUsageFactory(
            user=job.file.creator,
            submitted_at=timezone.now() - timedelta(hours=age_hours),
            duration_seconds=3600,
        )
        models.TranscriptionUsage.objects.filter(pk=history.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )
        post.return_value.json.return_value = {"job_id": "quota-transcript"}

        call_transcribe_service(job.pk)

    assert post.call_count == int(allowed)


@patch("core.tasks.file.session.post")
def test_transcription_quota_ignores_other_users_summaries_and_unsubmitted_jobs(post):
    """Only this user's submitted transcript jobs consume the audio allowance."""
    job = reserved_job()
    factories.TranscriptionUsageFactory(user=factories.UserFactory())
    history = {
        "file__creator": job.file.creator,
        "type": models.AiJobTypeChoices.TRANSCRIPT,
    }
    factories.AiFileJobFactory(**{**history, "type": models.AiJobTypeChoices.SUMMARIZE})
    factories.AiFileJobFactory(**history, remote_job_id=None)
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
    assert job.failure_reason == ""
    usage = models.TranscriptionUsage.objects.get(ai_job_id=job.pk)
    assert usage.duration_seconds == 3600
    assert usage.ignored is False


@patch("core.tasks.file.session.post")
def test_transcription_quota_ignored_charges_do_not_count(post):
    """Manual exemptions release capacity while retaining the original charge."""
    job = reserved_job(duration=3600)
    ignored = factories.TranscriptionUsageFactory(
        user=job.file.creator, ignored=True, ignored_reason="Support adjustment"
    )
    post.return_value.json.return_value = {"job_id": "new-transcript"}

    call_transcribe_service(job.pk)

    post.assert_called_once()
    ignored.refresh_from_db()
    assert ignored.ignored_reason == "Support adjustment"
    assert models.TranscriptionUsage.objects.filter(user=job.file.creator).count() == 2


@patch("core.tasks.file.session.post")
def test_transcription_quota_remains_reserved_between_automatic_retries(post):
    """A temporary transport error cannot free capacity for another submission."""
    job = reserved_job(duration=3600)
    post.side_effect = requests.Timeout("temporary failure")
    with pytest.raises(requests.Timeout):
        call_transcribe_service(job.pk)
    usage = models.TranscriptionUsage.objects.get(ai_job_id=job.pk)
    assert usage.ignored is False
    blocked = reserved_job(job.file.creator, duration=1)
    call_transcribe_service(blocked.pk)
    blocked.refresh_from_db()
    assert blocked.failure_reason == "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"
    post.assert_called_once()

    post.side_effect = None
    post.return_value.json.return_value = {"job_id": "recovered-transcript"}
    call_transcribe_service(job.pk)
    usage.refresh_from_db()
    assert usage.ignored is False
    assert models.TranscriptionUsage.objects.filter(ai_job_id=job.pk).count() == 1


@pytest.mark.parametrize(
    "failure", ["client_error", "invalid_response", "retry_exhausted"]
)
@patch("core.tasks.file.session.post")
def test_failed_transcription_releases_quota_for_manual_retry(post, failure):
    """Permanent failures retain ignored charges and allow a full-size manual retry."""
    job = reserved_job(duration=3600)
    if failure == "client_error":
        response = requests.Response()
        response.status_code = 400
        post.return_value = response
    elif failure == "invalid_response":
        post.return_value.json.return_value = {"job_id": None}
    else:
        post.side_effect = requests.Timeout("service unavailable")

    result = call_transcribe_service.apply(args=[job.pk], throw=False)

    assert result.failed()
    job.refresh_from_db()
    assert job.status == models.AiJobStatusChoices.FAILED
    usage = models.TranscriptionUsage.objects.get(ai_job_id=job.pk)
    assert usage.ignored is True
    assert usage.ignored_reason == "Transcription failed: UNKNOWN_FAILURE"

    post.reset_mock(side_effect=True, return_value=True)
    post.return_value.json.return_value = {"job_id": "manual-retry-transcript"}
    client = APIClient()
    client.force_login(job.file.creator)
    response = client.post(f"/api/v1.0/ai-jobs/{job.pk}/retry/", {"language": "fr"})

    assert response.status_code == 201, response.json()
    post.assert_called_once()
    retry_usage = models.TranscriptionUsage.objects.get(ai_job_id=response.json()["id"])
    assert retry_usage.ignored is False
    assert retry_usage.duration_seconds == 3600
    assert models.TranscriptionUsage.objects.filter(user=job.file.creator).count() == 2


def test_transcription_failure_preserves_existing_manual_ignore_reason():
    """Repeated failure handling does not overwrite a support explanation."""
    job = reserved_job()
    usage = factories.TranscriptionUsageFactory(
        ai_job_id=job.pk,
        user=job.file.creator,
        ignored=True,
        ignored_reason="Support adjustment",
    )

    job.mark_failed()

    usage.refresh_from_db()
    assert usage.ignored_reason == "Support adjustment"


@pytest.mark.parametrize("deleted_resource", ["file", "ai_job"])
@patch("core.tasks.file.session.post")
def test_transcription_quota_survives_deletion(post, deleted_resource):
    """Deleting source rows cannot refund audio; the charge expires after 24 hours."""
    job = reserved_job(duration=3600)
    user = job.file.creator
    source_job_id = job.pk
    post.return_value.json.return_value = {"job_id": "charged-transcript"}
    call_transcribe_service(job.pk)
    usage = models.TranscriptionUsage.objects.get(ai_job_id=source_job_id)

    if deleted_resource == "file":
        client = APIClient()
        client.force_login(user)
        url = f"/api/v1.0/files/{job.file_id}/"
        assert client.delete(url).status_code == 204
        with patch(
            "core.api.viewsets.process_file_deletion.delay",
            side_effect=process_file_deletion,
        ) as delete:
            assert client.delete(f"{url}hard-delete/").status_code == 204
        delete.assert_called_once()
        assert not models.File.objects.filter(pk=job.file_id).exists()
    else:
        job.delete()

    assert not models.AiFileJob.objects.filter(pk=source_job_id).exists()
    usage.refresh_from_db()
    assert usage.user_id == user.pk
    assert usage.duration_seconds == 3600
    blocked = reserved_job(user, duration=1)
    call_transcribe_service(blocked.pk)
    blocked.refresh_from_db()
    assert blocked.failure_reason == "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"
    post.assert_called_once()
    assert models.TranscriptionUsage.objects.filter(user=user).count() == 1

    admitted = reserved_job(user, duration=1)
    with patch(
        "core.tasks.file.timezone.now",
        return_value=usage.submitted_at + timedelta(hours=24),
    ):
        call_transcribe_service(admitted.pk)
    admitted.refresh_from_db()
    assert admitted.remote_job_id == "charged-transcript"
    assert post.call_count == 2
    assert models.TranscriptionUsage.objects.filter(user=user).count() == 2


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
    assert models.TranscriptionUsage.objects.filter(user=user).count() == 1
    for job in jobs:
        job.refresh_from_db()
    assert sorted(job.status for job in jobs) == ["failed", "pending"]
    assert [job.failure_reason for job in jobs].count(
        "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"
    ) == 1


@pytest.fixture(name="main_schema")
def fixture_main_schema():
    """Exercise the upgrade from main's schema and always restore current tables."""
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes("core")
    main_target = [("core", "0020_remove_file_audio_extraction_state")]
    try:
        executor.migrate(main_target)
        yield executor.loader.project_state(main_target).apps
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_quota_migrations_upgrade_main_schema_and_backfill_once(main_schema):
    """Upgrade main's real AI rows directly, preserving usage without temporary fields."""
    user = factories.UserFactory()
    file = factories.FileFactory(creator=user, duration_seconds=600)
    job_model = main_schema.get_model("core", "AiFileJob")
    assert not {
        "failure_reason",
        "submitted_at",
        "submitted_audio_duration_seconds",
    }.intersection(field.name for field in job_model._meta.get_fields())
    jobs = [
        job_model.objects.create(
            file_id=file.pk,
            type="transcript",
            status=status,
            remote_job_id=f"legacy-{index}",
            language="fr",
        )
        for index, status in enumerate(["failed", "success", "pending"])
    ]
    submitted_at = timezone.now() - timedelta(hours=6)
    job_model.objects.filter(pk__in=[job.pk for job in jobs]).update(
        created_at=submitted_at
    )
    excluded = [
        job_model.objects.create(
            file_id=file.pk, type=kind, status="pending", remote_job_id=remote_id
        )
        for kind, remote_id in [
            ("transcript", None),
            ("transcript", ""),
            ("summary", "legacy-summary"),
        ]
    ]
    excluded.append(
        job_model.objects.create(
            file_id=factories.FileFactory(creator=None).pk,
            type="transcript",
            status="pending",
            remote_job_id="legacy-ownerless",
        )
    )
    schema_target = [("core", "0021_aifilejob_submission_quota")]
    MigrationExecutor(connection).migrate(schema_target)
    schema_apps = MigrationExecutor(connection).loader.project_state(schema_target).apps
    migration = import_module("core.migrations.0022_backfill_aifilejob_submissions")
    with patch.object(migration, "BATCH_SIZE", 2):
        migration.backfill_submissions(schema_apps, connection.schema_editor())
        original_ids = set(
            models.TranscriptionUsage.objects.values_list("pk", flat=True)
        )
        migration.backfill_submissions(schema_apps, connection.schema_editor())
    MigrationExecutor(connection).migrate(
        [("core", "0022_backfill_aifilejob_submissions")]
    )

    assert (
        set(models.TranscriptionUsage.objects.values_list("pk", flat=True))
        == original_ids
    )
    assert len(original_ids) == 3
    assert (
        models.AiFileJob.objects.get(pk=jobs[0].pk).failure_reason == "UNKNOWN_FAILURE"
    )
    assert not models.TranscriptionUsage.objects.filter(
        ai_job_id__in=[job.pk for job in excluded]
    ).exists()
    for job in jobs:
        usage = models.TranscriptionUsage.objects.get(ai_job_id=job.pk)
        assert usage.user_id == user.pk
        assert usage.submitted_at == submitted_at
        assert usage.duration_seconds == 600
        assert usage.ignored == (job.status == "failed")
        assert usage.ignored_reason == (
            "Transcription failed: UNKNOWN_FAILURE" if job.status == "failed" else ""
        )

    blocked = reserved_job(user, duration=2401)
    with patch("core.tasks.file.session.post") as post:
        call_transcribe_service(blocked.pk)
    post.assert_not_called()
    blocked.refresh_from_db()
    assert blocked.failure_reason == "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"


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
