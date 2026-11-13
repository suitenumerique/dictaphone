"""Verified transfers, durable obligations, and policy-preserving cutover."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO, StringIO
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

import pytest

from core import factories, models
from core.configuration import clear_configuration_cache
from core.object_storage import (
    delete_file_objects,
    delete_object,
    publish_object,
    store_result,
)
from core.storage import get_storage_for_object
from core.storage_migration import cleanup_due, migrate_object

pytestmark = pytest.mark.django_db


@pytest.fixture(name="artifact")
def artifact_fixture(monkeypatch):
    """Two independent clients emulate cross-provider transfer and exact overwrites."""
    file = factories.FileFactory()
    file.upload_state = "ready"
    file.save(update_fields=["upload_state"])
    obj = file.original_object
    publish_object(obj, content=b"source bytes")
    source_bucket = obj.storage_bucket_name
    copies = {(source_bucket, obj.key): b"source bytes"}
    client = Mock()

    def read(**kwargs):
        content = copies[kwargs["Bucket"], kwargs["Key"]]
        return {
            "Body": BytesIO(content),
            "ContentLength": len(content),
            "ETag": '"destination-etag"',
            "ContentType": "audio/ogg",
            "Metadata": {"custom": "preserved"},
        }

    def upload(content, bucket, key, **_kwargs):
        copies[bucket, key] = content.read()

    client.get_object.side_effect = read
    client.upload_fileobj.side_effect = upload
    client.delete_object.side_effect = lambda **kw: copies.pop(
        (kw["Bucket"], kw["Key"]), None
    )
    storage = Mock()
    storage.connection.meta.client = client
    storage.delete.side_effect = lambda key: None
    monkeypatch.setattr(
        "core.storage_migration.get_storage_for_object", lambda obj: storage
    )
    monkeypatch.setattr(
        "core.storage_migration.expected_bucket", lambda obj: "destination"
    )
    return SimpleNamespace(
        file=file,
        obj=obj,
        client=client,
        storage=storage,
        copies=copies,
        source_bucket=source_bucket,
    )


def run(obj, **kwargs):
    """Exercise the public command with deterministic selection."""
    output = StringIO()
    call_command(
        "migrate_storage_objects", objects=[str(obj.pk)], stdout=output, **kwargs
    )
    return output.getvalue()


def test_transfer_preserves_identity_metadata_and_every_file_field(artifact):
    """Cutover preserves the complete file snapshot and exact artifact identity."""
    a = artifact
    before = models.File.objects.values().get(pk=a.file.pk)
    with patch.object(
        models.File, "save", side_effect=AssertionError("policy changed")
    ):
        assert "migrated=1" in run(a.obj)
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == "destination"
    assert a.obj.checksum_type == "FULL_OBJECT"
    assert a.obj.etag == '"destination-etag"'
    assert a.copies["destination", a.obj.key] == b"source bytes"
    assert models.File.objects.values().get(pk=a.file.pk) == before
    assert a.copies[a.source_bucket, a.obj.key] == b"source bytes"
    source = models.ObjectStorageObject.objects.get(
        storage_bucket_name=a.source_bucket, key=a.obj.key
    )
    assert source.state == "deleting"
    assert not cleanup_due(source)
    assert a.client.upload_fileobj.call_args.kwargs["ExtraArgs"] == {
        "ContentType": "audio/ogg",
        "Metadata": {"custom": "preserved"},
    }
    assert "aligned=1" in run(a.obj)


def test_overwrite_and_retry_after_interrupted_transfer(artifact):
    """An interrupted upload can be overwritten by a verified retry."""
    a = artifact
    upload = a.client.upload_fileobj.side_effect

    def interrupted(content, bucket, key, **kwargs):
        upload(content, bucket, key, **kwargs)
        raise OSError("interrupted after write")

    a.client.upload_fileobj.side_effect = interrupted
    with pytest.raises(CommandError, match="1 storage object"):
        run(a.obj, stderr=StringIO())
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == a.source_bucket
    leftover = models.ObjectStorageObject.objects.get(storage_bucket_name="destination")
    assert leftover.state == "deleting"
    assert cleanup_due(leftover)
    a.copies["destination", a.obj.key] = b"old partial bytes"
    a.client.upload_fileobj.side_effect = upload
    assert "migrated=1" in run(a.obj)
    assert a.copies["destination", a.obj.key] == b"source bytes"


def test_checksum_failure_leaves_source_authoritative(artifact):
    """A corrupted destination never becomes the authoritative location."""
    a = artifact
    a.client.upload_fileobj.side_effect = lambda content, bucket, key, **kw: (
        a.copies.update({(bucket, key): b"broken bytes"})
    )
    with pytest.raises(CommandError):
        run(a.obj, stderr=StringIO())
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == a.source_bucket
    assert (
        models.ObjectStorageObject.objects.get(storage_bucket_name="destination").state
        == "deleting"
    )


@pytest.mark.parametrize("change", ["pending", "temporary", "expired", "hard_deleted"])
def test_ineligible_objects_are_deferred(artifact, change):
    """Mutable, pending and expired artifacts never start a transfer."""
    a = artifact
    if change == "pending":
        models.ObjectStorageObject.objects.filter(pk=a.obj.pk).update(state="pending")
    elif change == "temporary":
        models.ObjectStorageObject.objects.filter(pk=a.obj.pk).update(kind="temporary")
    elif change == "expired":
        models.File.objects.filter(pk=a.file.pk).update(
            original_file_data_delete_at=timezone.now() - timedelta(seconds=1)
        )
    else:
        models.File.objects.filter(pk=a.file.pk).update(hard_deleted_at=timezone.now())
    assert "deferred=1" in run(a.obj)
    a.client.upload_fileobj.assert_not_called()


def test_audio_with_outstanding_signed_upload_is_deferred(artifact):
    """A completed worker may still hold a valid upload URL."""
    a = artifact
    audio = models.AudioJob.objects.create(
        file=a.file,
        mode="transcoding",
        status="success",
        expires_at=timezone.now() + timedelta(minutes=1),
    )
    publish_object(audio.output_object, content=b"source bytes")
    assert "deferred=1" in run(audio.output_object)


def test_expiry_during_transfer_prevents_cutover(artifact):
    """A transfer cannot republish original data after its deadline."""
    a = artifact
    upload = a.client.upload_fileobj.side_effect

    def expire(*args, **kwargs):
        upload(*args, **kwargs)
        models.File.objects.filter(pk=a.file.pk).update(
            original_file_data_delete_at=timezone.now() - timedelta(seconds=1)
        )

    a.client.upload_fileobj.side_effect = expire
    assert "deferred=1" in run(a.obj)
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == a.source_bucket


def test_other_artifact_destination_is_never_overwritten(artifact):
    """Tracked location collisions fail before sending bytes."""
    a = artifact
    other = factories.FileFactory()
    models.ObjectStorageObject.objects.create(
        file_identifier=other.pk,
        kind="original",
        key=a.obj.key,
        storage_bucket_name="destination",
    )
    with pytest.raises(CommandError):
        run(a.obj, stderr=StringIO())
    a.client.upload_fileobj.assert_not_called()


def test_dry_run_has_no_writes(artifact):
    """Planning leaves both storage and the tracked inventory unchanged."""
    a = artifact
    before = list(models.ObjectStorageObject.objects.values())

    def read_only(execute, sql, params, many, context):
        assert sql.lstrip().split()[0].upper() not in {"INSERT", "UPDATE", "DELETE"}
        return execute(sql, params, many, context)

    with connection.execute_wrapper(read_only):
        assert "migrated=1" in run(a.obj, dry_run=True)
    assert list(models.ObjectStorageObject.objects.values()) == before
    a.client.upload_fileobj.assert_not_called()
    a.client.get_object.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_source_cleanup_obeys_grace_deadline_and_file_deletion(artifact):
    """Retained URLs never outlive original-data deletion obligations."""
    a = artifact
    run(a.obj)
    source = models.ObjectStorageObject.objects.get(
        storage_bucket_name=a.source_bucket, key=a.obj.key
    )
    models.File.objects.filter(pk=a.file.pk).update(
        original_file_data_delete_at=timezone.now() - timedelta(minutes=2),
        original_file_data_delete_at_with_grace_period=timezone.now()
        - timedelta(minutes=1),
    )
    assert cleanup_due(source)
    with patch("core.object_storage.get_storage_for_object", return_value=a.storage):
        delete_file_objects(a.file)
    assert (
        not models.ObjectStorageObject.objects.filter(file_identifier=a.file.pk)
        .exclude(state="deleted")
        .exists()
    )


def test_writer_resolves_current_bucket_after_lock(artifact):
    """A stale writer instance cannot send content to the previous bucket."""
    a = artifact
    job = factories.AiFileJobFactory(file=a.file, type="summary")
    stale = job.result_object
    models.ObjectStorageObject.objects.filter(pk=stale.pk).update(
        storage_bucket_name="destination"
    )
    with patch(
        "core.object_storage.get_storage_for_object", return_value=a.storage
    ) as resolve:
        store_result(stale, b"summary", "text/plain")
    assert resolve.call_args.args[0].storage_bucket_name == "destination"
    assert a.client.put_object.call_args.kwargs["Bucket"] == "destination"


@pytest.mark.django_db(transaction=True)
def test_two_configured_s3_buckets(settings):
    """Integration: actual S3 clients, bucket credentials, upload and full read-back."""
    file = factories.FileFactory()
    file.upload_state = "ready"
    file.save(update_fields=["upload_state"])
    obj = file.original_object
    source = get_storage_for_object(obj)
    source.connection.meta.client.put_object(
        Bucket=obj.storage_bucket_name,
        Key=obj.key,
        Body=b"integration bytes",
        ContentType="audio/ogg",
        Metadata={"integration": "preserve"},
    )
    publish_object(obj, content=b"integration bytes")
    settings.DATA_POLICY_CONFIGURATIONS = {
        "default": {"default": True, "bucket": "alpha"}
    }
    clear_configuration_cache()
    try:
        assert migrate_object(obj.pk) == "migrated"
        obj.refresh_from_db()
        destination = get_storage_for_object(obj)
        response = destination.connection.meta.client.get_object(
            Bucket=obj.storage_bucket_name, Key=obj.key
        )
        assert response["Body"].read() == b"integration bytes"
        response["Body"].close()
        assert response["Metadata"] == {"integration": "preserve"}
    finally:
        delete_file_objects(file)


@pytest.mark.django_db(transaction=True)
def test_concurrent_migration_and_original_deletion(artifact):
    """Deletion holds its file lock while waiting; both physical copies are removed."""
    a = artifact
    transferring, deleting, release = Event(), Event(), Event()
    upload = a.client.upload_fileobj.side_effect
    deleted = []

    def slow_upload(*args, **kwargs):
        upload(*args, **kwargs)
        transferring.set()
        assert release.wait(10)

    def migrate():
        close_old_connections()
        try:
            return migrate_object(a.obj.pk)
        finally:
            close_old_connections()

    def remove():
        close_old_connections()
        try:
            with transaction.atomic():
                file = models.File.objects.select_for_update().get(pk=a.file.pk)
                models.File.objects.filter(pk=file.pk).update(
                    lifecycle_state="pending_original_data_deletion"
                )
                deleting.set()
                delete_file_objects(file, original_only=True)
                models.File.objects.filter(pk=file.pk).update(
                    lifecycle_state="original_data_deleted"
                )
        finally:
            close_old_connections()

    def storage_for(obj):
        storage = Mock()
        storage.delete.side_effect = lambda key: deleted.append(
            (obj.storage_bucket_name, key)
        )
        return storage

    a.client.upload_fileobj.side_effect = slow_upload
    with patch("core.object_storage.get_storage_for_object", side_effect=storage_for):
        with ThreadPoolExecutor(max_workers=2) as pool:
            transfer = pool.submit(migrate)
            assert transferring.wait(10)
            deletion = pool.submit(remove)
            assert deleting.wait(10)
            release.set()
            assert transfer.result(timeout=15) == "migrated"
            deletion.result(timeout=15)
    assert ("destination", a.obj.key) in deleted
    assert (a.source_bucket, a.obj.key) in deleted
    assert (
        not models.ObjectStorageObject.objects.filter(
            file_identifier=a.file.pk, kind__in=["original", "temporary", "audio"]
        )
        .exclude(state="deleted")
        .exists()
    )


def test_command_limit_batches_and_source_filter(artifact):
    """Selection filters and examined-object limits bound the run."""
    a = artifact
    output = StringIO()
    call_command(
        "migrate_storage_objects",
        files=[str(a.file.pk)],
        source_bucket="another-bucket",
        stdout=output,
    )
    assert "migrated=0" in output.getvalue()
    output = StringIO()
    call_command(
        "migrate_storage_objects",
        files=[str(a.file.pk)],
        batch_size=1,
        limit=1,
        stdout=output,
        dry_run=True,
    )
    assert (
        sum(output.getvalue().count(f"{state}=1") for state in ["migrated", "deferred"])
        == 1
    )


def test_completed_cleanup_reservation_can_be_retried(artifact):
    """A cleaned destination can be reserved again on a later retry."""
    a = artifact
    a.client.upload_fileobj.side_effect = OSError("interrupted")
    with pytest.raises(CommandError):
        run(a.obj, stderr=StringIO())
    with patch("core.object_storage.get_storage_for_object", return_value=a.storage):
        call_command("cleanup_storage_objects", stdout=StringIO())
    assert (
        models.ObjectStorageObject.objects.get(storage_bucket_name="destination").state
        == "deleted"
    )
    a.client.upload_fileobj.side_effect = lambda content, bucket, key, **kw: (
        a.copies.update({(bucket, key): content.read()})
    )
    assert "migrated=1" in run(a.obj)


@pytest.mark.django_db(transaction=True)
def test_process_interruption_keeps_committed_cleanup_record(artifact):
    """Process interruption rolls back cutover but retains its cleanup obligation."""
    a = artifact
    upload = a.client.upload_fileobj.side_effect

    def interrupt(*args, **kwargs):
        upload(*args, **kwargs)
        raise KeyboardInterrupt

    a.client.upload_fileobj.side_effect = interrupt
    with pytest.raises(KeyboardInterrupt):
        migrate_object(a.obj.pk)
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == a.source_bucket
    leftover = models.ObjectStorageObject.objects.get(storage_bucket_name="destination")
    assert leftover.state == "deleting"
    assert leftover.etag == str(a.obj.pk)
    with patch("core.object_storage.get_storage_for_object", return_value=a.storage):
        call_command("cleanup_storage_objects", stdout=StringIO())
    leftover.refresh_from_db()
    assert leftover.state == "deleted"


@pytest.mark.parametrize("kind", ["audio", "transcript", "summary"])
def test_job_references_are_unchanged(artifact, kind):
    """Audio and AI job references survive cutover without any job mutations."""
    a = artifact
    if kind == "audio":
        job = models.AudioJob.objects.create(
            file=a.file, mode="transcoding", status="success"
        )
        obj = job.output_object
    else:
        job = factories.AiFileJobFactory(file=a.file, type=kind, status="success")
        obj = job.result_object
    a.copies[a.source_bucket, obj.key] = b"source bytes"
    publish_object(obj, content=b"source bytes")
    before = type(job).objects.values().get(pk=job.pk)
    assert "migrated=1" in run(obj)
    assert type(job).objects.values().get(pk=job.pk) == before
    obj.refresh_from_db()
    assert obj.storage_bucket_name == "destination"


def test_cleanup_tolerates_reservation_removed_by_cutover(artifact):
    """Cleanup may have enumerated an obligation before cutover removed it."""
    a = artifact
    stale = models.ObjectStorageObject.objects.create(
        file_identifier=a.file.pk,
        key="stale",
        kind="original",
        storage_bucket_name="destination",
        state="deleting",
        checksum_source="migration",
    )
    pk = stale.pk
    stale.delete()
    stale.pk = pk
    assert delete_object(stale, respect_retention=True) is False
