"""Storage registration, metadata integrity, backfill, and durable cleanup."""

import base64
import hashlib
from io import BytesIO, StringIO
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

import pytest
from botocore.exceptions import ClientError
from storages.backends.s3 import S3Storage

from core import factories, models
from core.object_storage import (
    ObjectIntegrityError,
    delete_file_objects,
    head_object,
    observe_object,
    publish_object,
    store_result,
)
from core.storage import get_storage_for_file

pytestmark = pytest.mark.django_db


def test_new_artifacts_reserve_linked_locations():
    """All producers allocate references without falsely claiming content exists."""
    file = factories.FileFactory()
    audio = models.AudioJob.objects.create(file=file, mode="transcoding")
    validation = models.AudioJob.objects.create(
        file=file, mode="validation", source_job=audio
    )
    transcript = factories.AiFileJobFactory(
        file=file, type="transcript", status="pending"
    )
    assert file.original_object.key == file.file_key
    assert file.temporary_upload_object.key == file.temporary_file_key
    assert audio.output_object.key == audio.output_key
    assert validation.output_object is None
    assert transcript.result_object.key == transcript.key
    assert file.storage_objects.count() == 4
    assert not file.storage_objects.exclude(state="pending").exists()
    assert all(obj.file_identifier == file.pk for obj in file.storage_objects.all())


def test_reference_validation_rejects_wrong_file_and_kind():
    """An artifact cannot read another user's object through a misplaced reference."""
    file = factories.FileFactory()
    other = factories.FileFactory()
    file.original_object = other.original_object
    with pytest.raises(ValidationError, match="file and kind"):
        file.save()
    job = factories.AiFileJobFactory(file=other, type="summary")
    job.result_object = other.original_object
    with pytest.raises(ValidationError, match="file and kind"):
        job.save()


@pytest.mark.parametrize("checksum_type", ["FULL_OBJECT", "COMPOSITE"])
def test_head_observation_preserves_checksum_semantics(checksum_type):
    """Provider digest and opaque ETag are distinct; no bytes are downloaded."""
    obj = factories.FileFactory().original_object
    with patch(
        "core.object_storage.head_object",
        return_value={
            "ContentLength": 42,
            "ETag": '"opaque-3"',
            "ChecksumSHA256": "provider-digest",
            "ChecksumType": checksum_type,
        },
    ):
        assert observe_object(obj, publish=True)
    assert obj.state == "available"
    assert obj.size == 42
    assert obj.etag == '"opaque-3"'
    assert obj.checksum_algorithm == "SHA256"
    assert obj.checksum_value == "provider-digest"
    assert obj.checksum_type == checksum_type
    assert obj.checksum_source == "provider"


def test_checksumless_observation_preserves_existing_baseline():
    """A provider omitting checksum headers must not erase a known checksum."""
    obj = factories.FileFactory().original_object
    publish_object(obj, content=b"original")
    digest = obj.checksum_value
    with patch("core.object_storage.head_object", return_value={"ContentLength": 8}):
        observe_object(obj)
    assert obj.checksum_value == digest
    assert obj.checksum_source == "application"


def test_changed_provider_checksum_does_not_replace_baseline():
    """Comparable checksum mismatches are reported instead of silently accepted."""
    obj = factories.FileFactory().original_object
    publish_object(
        obj,
        head={
            "ContentLength": 4,
            "ChecksumSHA256": "baseline",
            "ChecksumType": "FULL_OBJECT",
        },
    )
    with patch(
        "core.object_storage.head_object",
        return_value={
            "ContentLength": 4,
            "ChecksumSHA256": "changed",
            "ChecksumType": "FULL_OBJECT",
        },
    ):
        with pytest.raises(ObjectIntegrityError, match="checksum changed"):
            observe_object(obj)
    obj.refresh_from_db()
    assert obj.checksum_value == "baseline"


def test_slow_head_cannot_overwrite_publication():
    """A metadata request finishing after a write cannot mark it missing."""
    obj = factories.FileFactory().original_object

    def concurrent_write(_obj):
        publish_object(_obj, content=b"new")

    with patch("core.object_storage.head_object", side_effect=concurrent_write):
        assert not observe_object(obj)
    assert obj.state == "available"
    assert obj.size == 3


@pytest.mark.parametrize("code", ["403", "AccessDenied", "500", "SlowDown"])
def test_head_errors_are_not_absence(code):
    """Authorization and provider failures cannot silently become missing objects."""
    obj = factories.FileFactory().original_object
    storage = Mock(spec=S3Storage)
    client = storage.connection.meta.client
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": code}}, "HeadObject"
    )
    with patch("core.object_storage.get_storage_for_object", return_value=storage):
        with pytest.raises(ClientError):
            head_object(obj)
    client.head_object.assert_called_once_with(
        Bucket=obj.storage_bucket_name,
        Key=obj.key,
        ChecksumMode="ENABLED",
    )


def test_head_checksum_unsupported_falls_back_without_download():
    """Explicit checksum API incompatibility allows a plain metadata request."""
    obj = factories.FileFactory().original_object
    storage = Mock(spec=S3Storage)
    client = storage.connection.meta.client
    client.head_object.side_effect = [
        ClientError({"Error": {"Code": "NotImplemented"}}, "HeadObject"),
        {"ContentLength": 4, "ETag": "opaque"},
    ]
    with patch("core.object_storage.get_storage_for_object", return_value=storage):
        assert head_object(obj)["ContentLength"] == 4
    assert client.head_object.call_count == 2
    client.get_object.assert_not_called()


def test_result_publication_is_immutable_and_idempotent():
    """Duplicate bytes reuse a result; different bytes cannot overwrite it."""
    job = factories.AiFileJobFactory(type="summary", status="pending")
    storage = Mock()
    store_result(job.result_object, storage, b"summary", "text/plain")
    store_result(job.result_object, storage, b"summary", "text/plain")
    with pytest.raises(ValueError, match="overwrite"):
        store_result(job.result_object, storage, b"changed", "text/plain")
    storage.connection.meta.client.put_object.assert_called_once()
    job.result_object.refresh_from_db()
    assert job.result_object.checksum_value == base64.b64encode(
        hashlib.sha256(b"summary").digest()
    ).decode("ascii")
    assert job.result_object.checksum_type == "FULL_OBJECT"


def test_missing_published_result_can_only_be_restored_with_identical_bytes():
    """Losing the physical copy must not discard its original integrity baseline."""
    job = factories.AiFileJobFactory(type="summary", status="pending")
    storage = Mock()
    store_result(job.result_object, storage, b"summary", "text/plain")
    models.ObjectStorageObject.objects.filter(pk=job.result_object_id).update(
        state="missing"
    )
    with pytest.raises(ValueError, match="overwrite"):
        store_result(job.result_object, storage, b"changed", "text/plain")
    store_result(job.result_object, storage, b"summary", "text/plain")
    assert storage.connection.meta.client.put_object.call_count == 2


def test_backfill_links_history_without_changing_policy():
    """Legacy, failed attempts, and results are registered idempotently."""
    file = factories.FileFactory()
    audio = models.AudioJob.objects.create(
        file=file, mode="transcoding", status="failed"
    )
    ai = factories.AiFileJobFactory(file=file, type="transcript", status="success")
    deadlines = (file.original_file_data_delete_at, file.file_auto_hard_delete_at)
    # Simulate records created before the tracking schema was deployed.
    file.storage_objects.all().delete()
    file.refresh_from_db()
    with patch(
        "core.object_storage.head_object",
        return_value={
            "ContentLength": 9,
            "ChecksumCRC32C": "crc",
            "ChecksumType": "FULL_OBJECT",
        },
    ) as head:
        call_command("backfill_storage_objects", batch_size=1, stdout=StringIO())
        call_command("backfill_storage_objects", stdout=StringIO())
    file.refresh_from_db()
    audio.refresh_from_db()
    ai.refresh_from_db()
    assert file.storage_objects.count() == 5
    assert audio.output_object.key == audio.output_key
    assert ai.result_object.state == "available"
    assert ai.result_object.checksum_algorithm == "CRC32C"
    assert file.temporary_upload_object.state == "pending"
    assert (
        file.original_file_data_delete_at,
        file.file_auto_hard_delete_at,
    ) == deadlines
    assert head.call_count == 10


def test_backfill_dry_run_does_not_create_or_update_records():
    """Dry run may read metadata but leaves both registry and owner links unchanged."""
    file = factories.FileFactory()
    file.storage_objects.all().delete()
    with patch("core.object_storage.head_object", return_value=None):
        call_command("backfill_storage_objects", dry_run=True, stdout=StringIO())
    file.refresh_from_db()
    assert file.original_object_id is None
    assert not models.ObjectStorageObject.objects.exists()


def test_backfill_missing_required_objects_fails_but_optional_absence_is_reported():
    """Absent originals are only errors when lifecycle and upload state require them."""
    file = factories.FileFactory(update_upload_state="ready")
    with patch("core.object_storage.head_object", return_value=None):
        with pytest.raises(CommandError, match="incomplete"):
            call_command(
                "backfill_storage_objects", stdout=StringIO(), stderr=StringIO()
            )
        file.lifecycle_state = models.FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
        file.save()
        call_command("backfill_storage_objects", stdout=StringIO())
    file.original_object.refresh_from_db()
    assert file.original_object.state == "missing"


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("missing", [False, True])
def test_backfill_duplicate_key_preserves_requiredness(dry_run, missing):
    """A successful job requires its output even when a legacy candidate is optional."""
    file = factories.FileFactory(update_upload_state="ready")
    audio = models.AudioJob.objects.create(
        file=file,
        mode="transcoding",
        status="success",
        output_key=file.legacy_audio_file_key,
    )
    stdout = StringIO()

    def head_response(obj):
        if missing and obj.key == audio.output_key:
            return None
        return {"ContentLength": 9}

    head_target = (
        "core.management.commands.backfill_storage_objects.head_object"
        if dry_run
        else "core.object_storage.head_object"
    )
    with patch(head_target, side_effect=head_response) as head:
        if missing:
            with pytest.raises(CommandError, match="incomplete"):
                call_command(
                    "backfill_storage_objects",
                    dry_run=dry_run,
                    stdout=stdout,
                    stderr=StringIO(),
                )
        else:
            call_command("backfill_storage_objects", dry_run=dry_run, stdout=stdout)
    assert head.call_count == 3
    assert {call.args[0].key for call in head.call_args_list} == {
        file.file_key,
        file.temporary_file_key,
        audio.output_key,
    }
    assert "objects=3" in stdout.getvalue()
    assert f"expected_missing={int(missing)}" in stdout.getvalue()
    audio.output_object.refresh_from_db()
    if dry_run:
        assert audio.output_object.state == "pending"
    else:
        assert audio.output_object.state == ("missing" if missing else "available")
        assert bool(audio.output_object.published_at) is not missing


def test_backfill_limit_cursor_and_skip_head():
    """A bounded run can resume without scanning or reading object content."""
    files = sorted(
        [factories.FileFactory(), factories.FileFactory()], key=lambda file: file.pk
    )
    for file in files:
        file.storage_objects.all().delete()
    with patch("core.object_storage.head_object") as head:
        call_command(
            "backfill_storage_objects", limit=1, skip_head=True, stdout=StringIO()
        )
        files[0].refresh_from_db()
        files[1].refresh_from_db()
        assert files[0].original_object_id is not None
        assert files[1].original_object_id is None
        call_command(
            "backfill_storage_objects",
            after_file_id=files[0].pk,
            skip_head=True,
            stdout=StringIO(),
        )
        head.assert_not_called()
    files[1].refresh_from_db()
    assert files[1].original_object_id is not None


def test_original_cleanup_preserves_results_and_tombstones_survive_file():
    """Original-data retention excludes results; full cleanup preserves audit identity."""
    file = factories.FileFactory()
    job = factories.AiFileJobFactory(file=file, type="summary", status="success")
    storage = get_storage_for_file(file)
    storage.save(file.file_key, BytesIO(b"original"))
    storage.save(job.key, BytesIO(b"summary"))
    delete_file_objects(file, original_only=True)
    assert not storage.exists(file.file_key)
    assert storage.exists(job.key)
    delete_file_objects(file)
    identity = file.pk
    file.deleted_at = timezone.now()
    file.save()
    file.delete()
    objects = models.ObjectStorageObject.objects.filter(file_identifier=identity)
    assert objects.exists()
    assert not objects.exclude(state="deleted", file__isnull=True).exists()


def test_failed_cleanup_can_be_retried_after_owner_job_deletion(
    django_capture_on_commit_callbacks,
):
    """An on-commit storage failure leaves an independently addressable cleanup record."""
    job = factories.AiFileJobFactory(type="summary", status="success")
    job_id = job.pk
    obj = job.result_object
    with patch("core.object_storage.get_storage_for_object") as storage:
        storage.return_value.delete.side_effect = OSError("unavailable")
        with pytest.raises(OSError):
            with django_capture_on_commit_callbacks(execute=True):
                job.delete()
    assert not models.AiFileJob.objects.filter(pk=job_id).exists()
    obj.refresh_from_db()
    assert obj.state == "deleting"
    with patch("core.object_storage.get_storage_for_object") as storage:
        call_command("cleanup_storage_objects", stdout=StringIO())
        storage.return_value.delete.assert_called_once_with(obj.key)
    obj.refresh_from_db()
    assert obj.state == "deleted"
