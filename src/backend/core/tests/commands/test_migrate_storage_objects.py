"""Verified transfers, durable obligations, and policy-preserving cutover."""

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
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

    def bucket_storage(bucket_name):
        client = Mock()

        def read(**params):
            assert params["Bucket"] == bucket_name
            content = copies[params["Bucket"], params["Key"]]
            return {
                "Body": BytesIO(content),
                "ContentLength": len(content),
                "ETag": '"destination-etag"',
                "ContentType": "audio/ogg",
                "Metadata": {"custom": "preserved"},
            }

        def upload(filename, bucket, key, **_kwargs):
            assert bucket == bucket_name
            copies[bucket, key] = Path(filename).read_bytes()

        def put(**params):
            assert params["Bucket"] == bucket_name
            body = params["Body"]
            copies[bucket_name, params["Key"]] = (
                body if isinstance(body, bytes) else body.read()
            )

        client.get_object.side_effect = read
        client.upload_file.side_effect = upload
        client.put_object.side_effect = put
        storage = Mock()
        storage.connection.meta.client = client
        storage.delete.side_effect = lambda key: copies.pop((bucket_name, key), None)
        return storage

    storages = {
        source_bucket: bucket_storage(source_bucket),
        "destination": bucket_storage("destination"),
    }

    def storage_for(obj):
        return storages[obj.storage_bucket_name]

    monkeypatch.setattr("core.storage_migration.get_storage_for_object", storage_for)
    monkeypatch.setattr("core.object_storage.get_storage_for_object", storage_for)
    monkeypatch.setattr(
        "core.storage_migration.get_bucket_configuration_for_object",
        lambda obj: SimpleNamespace(
            upload_acl="private" if obj.storage_bucket_name == "destination" else None
        ),
    )
    monkeypatch.setattr(
        "core.storage_migration.expected_bucket", lambda file: "destination"
    )
    return SimpleNamespace(
        file=file,
        obj=obj,
        client=storages["destination"].connection.meta.client,
        source_client=storages[source_bucket].connection.meta.client,
        storage_for=storage_for,
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
    assert a.client.upload_file.call_args.kwargs["ExtraArgs"] == {
        "ACL": "private",
        "ContentType": "audio/ogg",
        "Metadata": {"custom": "preserved"},
    }
    assert "aligned=1" in run(a.obj)


def test_overwrite_and_retry_after_interrupted_transfer(artifact):
    """An interrupted upload can be overwritten by a verified retry."""
    a = artifact
    upload = a.client.upload_file.side_effect

    def interrupted(content, bucket, key, **kwargs):
        upload(content, bucket, key, **kwargs)
        raise OSError("interrupted after write")

    a.client.upload_file.side_effect = interrupted
    with pytest.raises(CommandError, match="1 storage object"):
        run(a.obj, stderr=StringIO())
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == a.source_bucket
    leftover = models.ObjectStorageObject.objects.get(storage_bucket_name="destination")
    assert leftover.state == "deleting"
    assert cleanup_due(leftover)
    a.copies["destination", a.obj.key] = b"old partial bytes"
    a.client.upload_file.side_effect = upload
    assert "migrated=1" in run(a.obj)
    assert a.copies["destination", a.obj.key] == b"source bytes"


@pytest.mark.parametrize(
    ("upload_limit_mib", "part_size_mib"),
    [(1, 5), (1024, 1024), (8192, 5120)],
)
def test_upload_uses_one_part_up_to_the_file_limit(
    artifact, settings, upload_limit_mib, part_size_mib
):
    """Objects within FILE_UPLOAD_MAX_SIZE take one PUT; the copy is read back."""
    a = artifact
    settings.FILE_UPLOAD_MAX_SIZE = upload_limit_mib * 1024**2
    assert "migrated=1" in run(a.obj)
    a.client.upload_file.assert_called_once()
    config = a.client.upload_file.call_args.kwargs["Config"]
    assert config.multipart_chunksize == part_size_mib * 1024**2
    # s3transfer switches to multipart at sizes >= the threshold.
    assert config.multipart_threshold == part_size_mib * 1024**2 + 1
    assert config.preferred_transfer_client == "classic"
    a.source_client.get_object.assert_called_once_with(
        Bucket=a.source_bucket, Key=a.obj.key
    )
    a.client.get_object.assert_called_once_with(Bucket="destination", Key=a.obj.key)


def test_aligned_dry_run_loads_file_and_creator_together(django_assert_num_queries):
    """The routing check reuses the owning file read used for eligibility."""
    file = factories.FileFactory(update_upload_state="ready")
    obj = file.original_object
    publish_object(obj, content=b"source bytes")

    with django_assert_num_queries(2):
        assert migrate_object(obj.pk, dry_run=True) == "aligned"


def test_checksum_failure_leaves_source_authoritative(artifact):
    """A corrupted destination never becomes the authoritative location."""
    a = artifact
    a.client.upload_file.side_effect = lambda content, bucket, key, **kw: (
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


@pytest.mark.parametrize(
    ("algorithm", "hex_digest"),
    [
        ("SHA1", "f7c3bc1d808e04732adf679965ccc34ca7ae3441"),
        ("CRC32", "cbf43926"),
        ("CRC32C", "e3069283"),
        ("CRC64NVME", "ae8b14860a799888"),
    ],
)
@pytest.mark.parametrize("matches", [True, False])
def test_verify_full_object_baseline(
    artifact, monkeypatch, algorithm, hex_digest, matches
):
    """Verify supported baselines against the entire source across chunk boundaries."""
    a = artifact
    a.copies[a.source_bucket, a.obj.key] = b"123456789"
    checksum = base64.b64encode(bytes.fromhex(hex_digest)).decode("ascii")
    models.ObjectStorageObject.objects.filter(pk=a.obj.pk).update(
        checksum_algorithm=algorithm,
        checksum_value=checksum if matches else "different",
        size=9,
    )
    monkeypatch.setattr("core.storage_migration.CHUNK_SIZE", 4)
    if matches:
        assert "migrated=1" in run(a.obj)
    else:
        stderr = StringIO()
        with pytest.raises(CommandError, match="1 storage object"):
            run(a.obj, stderr=stderr)
        assert stderr.getvalue() == f"object={a.obj.pk}: ObjectIntegrityError\n"
        a.client.upload_file.assert_not_called()


@pytest.mark.parametrize(
    ("checksum_type", "outcome"),
    [
        ("FULL_OBJECT", "deferred"),
        ("COMPOSITE", "migrated"),
    ],
)
def test_unrecognized_checksum_baseline(artifact, checksum_type, outcome):
    """Only a full-object baseline must be recognized to allow migration."""
    a = artifact
    models.ObjectStorageObject.objects.filter(pk=a.obj.pk).update(
        checksum_type=checksum_type, checksum_algorithm="unknown"
    )
    assert f"{outcome}=1" in run(a.obj, dry_run=True)
    assert f"{outcome}=1" in run(a.obj)
    if outcome == "deferred":
        a.source_client.get_object.assert_not_called()
        a.client.upload_file.assert_not_called()


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
    a.client.upload_file.assert_not_called()


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
    upload = a.client.upload_file.side_effect

    def expire(*args, **kwargs):
        upload(*args, **kwargs)
        models.File.objects.filter(pk=a.file.pk).update(
            original_file_data_delete_at=timezone.now() - timedelta(seconds=1)
        )

    a.client.upload_file.side_effect = expire
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
    a.client.upload_file.assert_not_called()


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
    a.client.upload_file.assert_not_called()
    a.client.get_object.assert_not_called()
    a.source_client.get_object.assert_not_called()


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
        "core.object_storage.get_storage_for_object", wraps=a.storage_for
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
    upload = a.client.upload_file.side_effect
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

    a.client.upload_file.side_effect = slow_upload
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


@pytest.mark.parametrize(
    ("selector", "option", "value"),
    [
        ("objects", "--object", ["invalid"]),
        ("files", "--file", ["invalid"]),
        ("source_bucket", "--source-bucket", ""),
        ("start_after", "--start-after", "invalid"),
    ],
)
def test_command_rejects_invalid_selectors(
    django_assert_num_queries, selector, option, value
):
    """Reject malformed options before enumerating any row."""
    with django_assert_num_queries(0), pytest.raises(CommandError, match=option):
        call_command("migrate_storage_objects", **{selector: value})


def test_command_resumes_after_last_examined_deferred_object(artifact):
    """The cursor is exclusive and advances even when a row is deferred."""
    a = artifact
    ids = sorted([a.obj.pk, a.file.temporary_upload_object_id])
    models.ObjectStorageObject.objects.filter(pk=ids[0]).update(state="pending")
    options = {"objects": [str(pk) for pk in ids], "dry_run": True, "limit": 1}
    first, next_run = StringIO(), StringIO()
    call_command("migrate_storage_objects", stdout=first, **options)
    assert f"{ids[0]}: deferred" in first.getvalue()
    assert f"Last examined PK: {ids[0]}" in first.getvalue()
    call_command(
        "migrate_storage_objects", start_after=ids[0], stdout=next_run, **options
    )
    assert f"Last examined PK: {ids[1]}" in next_run.getvalue()
    assert str(ids[0]) not in next_run.getvalue()


def test_reverse_migration_preserves_retained_source(artifact, monkeypatch):
    """A reverse migration cannot reserve or overwrite a retained source."""
    a = artifact
    assert "migrated=1" in run(a.obj)
    source = models.ObjectStorageObject.objects.filter(
        storage_bucket_name=a.source_bucket, key=a.obj.key
    )
    before = source.values().get()
    monkeypatch.setattr(
        "core.storage_migration.expected_bucket", lambda file: a.source_bucket
    )
    a.source_client.upload_file.side_effect = OSError("reverse upload failed")
    assert "deferred=1" in run(a.obj, dry_run=True)
    assert "deferred=1" in run(a.obj)
    a.source_client.upload_file.assert_not_called()
    call_command("cleanup_storage_objects", stdout=StringIO())
    assert source.values().get() == before
    assert a.copies[a.source_bucket, a.obj.key] == b"source bytes"
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == "destination"

    source.update(metadata_checked_at=timezone.now() - timedelta(seconds=1))
    assert "migrated=1" in run(a.obj, dry_run=True)
    with pytest.raises(CommandError, match="1 storage object"):
        run(a.obj, stderr=StringIO())
    assert "ACL" not in a.source_client.upload_file.call_args.kwargs["ExtraArgs"]


def test_completed_cleanup_reservation_can_be_retried(artifact):
    """A cleaned destination can be reserved again on a later retry."""
    a = artifact
    upload = a.client.upload_file.side_effect
    a.client.upload_file.side_effect = OSError("interrupted")
    with pytest.raises(CommandError):
        run(a.obj, stderr=StringIO())
    call_command("cleanup_storage_objects", stdout=StringIO())
    assert (
        models.ObjectStorageObject.objects.get(storage_bucket_name="destination").state
        == "deleted"
    )
    a.client.upload_file.side_effect = upload
    assert "migrated=1" in run(a.obj)


@pytest.mark.django_db(transaction=True)
def test_process_interruption_keeps_committed_cleanup_record(artifact):
    """Process interruption rolls back cutover but retains its cleanup obligation."""
    a = artifact
    upload = a.client.upload_file.side_effect

    def interrupt(*args, **kwargs):
        upload(*args, **kwargs)
        raise KeyboardInterrupt

    a.client.upload_file.side_effect = interrupt
    with pytest.raises(KeyboardInterrupt):
        migrate_object(a.obj.pk)
    a.obj.refresh_from_db()
    assert a.obj.storage_bucket_name == a.source_bucket
    leftover = models.ObjectStorageObject.objects.get(storage_bucket_name="destination")
    assert leftover.state == "deleting"
    assert leftover.etag == str(a.obj.pk)
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
