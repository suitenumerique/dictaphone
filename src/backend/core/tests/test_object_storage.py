"""Storage registration, metadata integrity, and durable cleanup."""

import base64
import hashlib
from datetime import timedelta
from io import BytesIO, StringIO
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone

import pytest
from botocore.exceptions import BotoCoreError, ClientError
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
from core.storage import get_storage_for_object
from core.tasks.file import process_file_deletion, process_original_file_data_deletion

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
    assert file.original_object.key.endswith(f"/{file.pk}.{file.extension}")
    assert file.temporary_upload_object.kind == "temporary"
    assert audio.output_object.key.endswith(f"/audio/{audio.pk}.ogg")
    assert validation.output_object is None
    assert transcript.result_object.key == f"transcripts/{transcript.pk}.json"
    assert file.storage_objects.count() == 4
    assert file.original_object.file_id == file.pk
    assert file.temporary_upload_object.file_id == file.pk
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


@pytest.mark.django_db(transaction=True)
def test_original_cleanup_preserves_results_and_tombstones_survive_file():
    """Original-data retention excludes results; full cleanup preserves audit identity."""
    file = factories.FileFactory()
    job = factories.AiFileJobFactory(file=file, type="summary", status="success")
    storage = get_storage_for_object(file.original_object)
    storage.save(file.original_object.key, BytesIO(b"original"))
    storage.save(job.result_object.key, BytesIO(b"summary"))
    delete_file_objects(file, original_only=True)
    assert not storage.exists(file.original_object.key)
    assert storage.exists(job.result_object.key)
    delete_file_objects(file)
    identity = file.pk
    file.deleted_at = timezone.now()
    file.save()
    file.delete()
    objects = models.ObjectStorageObject.objects.filter(file_identifier=identity)
    assert objects.exists()
    assert not objects.exclude(state="deleted", file__isnull=True).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "task", [process_file_deletion, process_original_file_data_deletion]
)
def test_lifecycle_cleanup_commits_all_tombstones_before_storage_failure(task):
    """A failed post-commit deletion leaves the whole batch available for recovery."""
    file = factories.FileFactory()
    factories.AiFileJobFactory(file=file, type="summary")
    file_id = file.pk
    if task is process_file_deletion:
        file.soft_delete()
        file.hard_delete()
    expected_count = 3 if task is process_file_deletion else 2

    def fail_after_commit(_obj):
        assert not connection.in_atomic_block
        objects = models.ObjectStorageObject.objects.filter(file_identifier=file_id)
        assert objects.filter(state="deleting").count() == expected_count
        raise OSError("unavailable")

    with patch(
        "core.object_storage.delete_object", side_effect=fail_after_commit
    ) as delete:
        with pytest.raises(OSError, match="unavailable"):
            with transaction.atomic():
                task(file_id)
                delete.assert_not_called()
        delete.assert_called_once()

    objects = models.ObjectStorageObject.objects.filter(file_identifier=file_id)
    assert objects.filter(state="deleting").count() == expected_count
    with patch("core.object_storage.get_storage_for_object") as storage:
        call_command("cleanup_storage_objects", stdout=StringIO())
    assert storage.return_value.delete.call_count == expected_count
    assert objects.filter(state="deleted").count() == expected_count
    if task is process_file_deletion:
        assert not models.File.objects.filter(pk=file_id).exists()
        assert not objects.filter(file__isnull=False).exists()
    else:
        assert objects.get(kind="summary").state == "pending"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "task", [process_file_deletion, process_original_file_data_deletion]
)
def test_lifecycle_cleanup_rollback_does_not_delete_storage(task):
    """Rolling back cleanup intent must discard the physical deletion callback."""
    file = factories.FileFactory()
    file_id = file.pk
    if task is process_file_deletion:
        file.soft_delete()
        file.hard_delete()
    with patch("core.object_storage.get_storage_for_object") as storage:
        with pytest.raises(RuntimeError, match="rollback"):
            with transaction.atomic():
                task(file_id)
                raise RuntimeError("rollback")
    storage.assert_not_called()
    file.refresh_from_db()
    assert file.lifecycle_state == models.FileLifecycleStateChoices.ACTIVE
    assert not file.storage_objects.exclude(state="pending").exists()


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


@pytest.mark.parametrize(
    "error",
    [
        OSError("private provider response"),
        BotoCoreError(),
        ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject"),
    ],
)
def test_cleanup_continues_after_individual_deletion_failures(error):
    """Failed objects remain retryable while later objects are still deleted."""
    job = factories.AiFileJobFactory()
    objects = list(job.file.storage_objects.order_by("pk"))
    assert len(objects) == 3
    job.file.storage_objects.update(state="deleting")
    stdout, stderr = StringIO(), StringIO()
    with patch("core.object_storage.get_storage_for_object") as storage:
        storage.return_value.delete.side_effect = [error, error, None]
        with pytest.raises(CommandError, match="2 deletions failed"):
            call_command("cleanup_storage_objects", stdout=stdout, stderr=stderr)
    assert [call.args[0] for call in storage.return_value.delete.call_args_list] == [
        obj.key for obj in objects
    ]
    assert stdout.getvalue() == "Deleted: 1\n"
    assert stderr.getvalue().splitlines() == [
        f"object={obj.pk}: {type(error).__name__}" for obj in objects[:2]
    ]
    for obj, state in zip(objects, ["deleting", "deleting", "deleted"], strict=True):
        obj.refresh_from_db()
        assert obj.state == state


def test_cleanup_dry_run_preserves_deleting_objects():
    """Dry runs count the bounded batch without attempting deletion."""
    file = factories.FileFactory()
    file.storage_objects.update(state="deleting")
    stdout = StringIO()
    with patch(
        "core.management.commands.cleanup_storage_objects.delete_object"
    ) as delete:
        call_command("cleanup_storage_objects", dry_run=True, limit=1, stdout=stdout)
    delete.assert_not_called()
    assert stdout.getvalue() == "Would delete: 1\n"
    assert not file.storage_objects.exclude(state="deleting").exists()
