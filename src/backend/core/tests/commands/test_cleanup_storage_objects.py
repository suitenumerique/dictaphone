"""Exercise cleanup of storage artifacts from failed jobs."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

import pytest

from core import factories, models
from core.tasks.file import handle_transcript_received

pytestmark = pytest.mark.django_db


def test_failed_ai_job_deletes_migrated_artifacts_after_commit(
    django_capture_on_commit_callbacks,
):
    """Delete both bucket locations only after the failure transaction commits."""
    job = factories.AiFileJobFactory(status="pending", type="summary")
    result = job.result_object
    # A completed cutover leaves the old key available for previously issued URLs.
    # The migration record links back to the authoritative result through its ETag field.
    copy = job.file.storage_objects.create(
        file_identifier=job.file_id,
        kind=result.kind,
        storage_bucket_name="previous-bucket",
        key=result.key,
        state="deleting",
        checksum_source="migration",
        etag=str(result.pk),
        published_at=timezone.now(),
        metadata_checked_at=timezone.now() + timedelta(days=1),
    )
    with patch("core.object_storage.get_storage_for_object") as storage:
        with django_capture_on_commit_callbacks(execute=True):
            job.mark_failed()
            storage.assert_not_called()
    assert {
        (call.args[0].storage_bucket_name, call.args[0].key)
        for call in storage.call_args_list
    } == {(obj.storage_bucket_name, obj.key) for obj in (result, copy)}
    # The job still references its result row. The old location was only a cleanup record.
    result.refresh_from_db()
    assert result.state == "deleted"
    assert not job.file.storage_objects.filter(pk=copy.pk).exists()


def test_job_cleanup_backfills_and_expires_only_selected_jobs():
    """Preview job selection, release quota on expiry, and honor active audio leases."""
    file = factories.FileFactory()
    jobs = [
        factories.AiFileJobFactory(file=file, status=status, type="transcript")
        for status in ("pending", "pending", "failed", "success")
    ]
    stuck, _recent, failed, successful = jobs
    # Give a pending and a successful job the same age to exercise the status filter.
    models.AiFileJob.objects.filter(pk__in=[stuck.pk, successful.pk]).update(
        created_at=timezone.now() - timedelta(hours=49)
    )
    usage = factories.TranscriptionUsageFactory(ai_job_id=stuck.pk, user=file.creator)
    audio = models.AudioJob.objects.create(
        file=file,
        mode="transcoding",
        status="failed",
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    stdout = StringIO()
    options = {"failed_jobs": True, "pending_ai_hours": 48}
    with patch("core.object_storage.get_storage_for_object") as storage:
        call_command("cleanup_storage_objects", dry_run=True, stdout=stdout, **options)
        assert "Would fail pending AI jobs: 1" in stdout.getvalue()
        assert "Would queue failed job objects: 2" in stdout.getvalue()
        storage.assert_not_called()
        stuck.refresh_from_db()
        assert stuck.status == "pending"

        call_command("cleanup_storage_objects", stdout=StringIO(), **options)
        assert {call.args[0].pk for call in storage.call_args_list} == {
            stuck.result_object_id,
            failed.result_object_id,
        }
        audio.output_object.refresh_from_db()
        assert audio.output_object.state == "deleting"

        # A regular cron run can finish the queued audio deletion after its URL expires.
        models.AudioJob.objects.filter(pk=audio.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        storage.reset_mock()
        call_command("cleanup_storage_objects", stdout=StringIO())
        assert storage.call_args.args[0].pk == audio.output_object_id

    for job, status, object_state in zip(
        jobs,
        ("failed", "pending", "failed", "success"),
        ("deleted", "pending", "deleted", "pending"),
        strict=True,
    ):
        job.refresh_from_db()
        assert job.status == status
        assert job.result_object.state == object_state
    usage.refresh_from_db()
    assert usage.ignored


def test_late_result_cannot_revive_expired_job():
    """A result already in flight cannot write after maintenance fails its job."""
    job = factories.AiFileJobFactory(status="pending", type="transcript")
    models.AiFileJob.objects.filter(pk=job.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )

    def download_result(*_args):
        """Run maintenance after the result handler has loaded the pending job."""
        call_command("cleanup_storage_objects", pending_ai_hours=1, stdout=StringIO())
        return b'{"segments": [], "word_segments": []}'

    with (
        patch("core.tasks.file.fetch_external_source"),
        patch("core.tasks.file.read_response", side_effect=download_result),
        patch("core.tasks.file.store_result") as store,
        patch("core.object_storage.get_storage_for_object"),
    ):
        handle_transcript_received(job.remote_job_id, "https://example.com/result")
        store.assert_not_called()

    job.refresh_from_db()
    assert job.status == "failed"
    assert job.result_object.state == "deleted"
