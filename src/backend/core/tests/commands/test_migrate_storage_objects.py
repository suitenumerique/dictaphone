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
from botocore.exceptions import ClientError

from core import factories, models, storage_migration
from core.configuration import clear_configuration_cache
from core.management.commands import migrate_storage_objects
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
        client.head_object.side_effect = lambda **params: {
            "ContentLength": len(copies[params["Bucket"], params["Key"]]),
            "ETag": '"destination-etag"',
        }
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


@pytest.mark.parametrize("lifecycle", ["active", "pending_original_data_deletion"])
def test_transfer_preserves_identity_metadata_and_every_file_field(artifact, lifecycle):
    """Cutover preserves the complete file snapshot and exact artifact identity."""
    a = artifact
    models.File.objects.filter(pk=a.file.pk).update(
        lifecycle_state=lifecycle,
        original_file_data_delete_at=timezone.now() - timedelta(minutes=1),
    )
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


@pytest.mark.parametrize("destination_state", [None, "deleting", "deleted", "pending"])
@pytest.mark.parametrize("source_state", ["missing", "deleted"])
def test_absent_object_moves_only_its_record(artifact, destination_state, source_state):
    """Preserve the recorded state and respect tracked destination ownership."""
    a = artifact
    objects = models.ObjectStorageObject.objects
    now = timezone.now()
    is_deleted = source_state == "deleted"
    objects.filter(pk=a.obj.pk).update(
        state=source_state,
        metadata_checked_at=now,
        deleted_at=now if is_deleted else None,
    )
    if is_deleted:
        models.File.objects.filter(pk=a.file.pk).update(
            original_file_data_delete_at=now - timedelta(seconds=1)
        )
    a.copies.clear()
    if destination_state is not None:
        objects.create(
            file_identifier=a.file.pk,
            kind=a.obj.kind,
            key=a.obj.key,
            storage_bucket_name="destination",
            state=destination_state,
            checksum_source="migration",
            etag=str(a.obj.pk),
        )
    before = list(objects.order_by("pk").values())
    outcome = {"deleting": "deferred", "pending": "failed"}.get(
        destination_state, "migrated"
    )
    with patch.object(
        storage_migration, "get_storage_for_object", side_effect=AssertionError
    ):
        for dry_run in (True, False):
            if outcome == "failed":
                with pytest.raises(CommandError, match="1 storage object"):
                    run(a.obj, dry_run=dry_run, stderr=StringIO())
            else:
                assert f"{outcome}=1" in run(
                    a.obj, dry_run=dry_run, source_bucket=a.source_bucket
                )
            if dry_run or outcome != "migrated":
                assert list(objects.order_by("pk").values()) == before
    if outcome == "migrated":
        source = next(row for row in before if row["id"] == a.obj.pk)
        after = objects.values().get(pk=a.obj.pk)
        source.update(storage_bucket_name="destination", updated_at=after["updated_at"])
        assert after == source
        a.file.refresh_from_db()
        assert a.file.original_object_id == a.obj.pk
        assert list(objects.filter(key=a.obj.key).values_list("pk", flat=True)) == [
            a.obj.pk
        ]
        assert "aligned=1" in run(a.obj)


@pytest.mark.parametrize("state", ["missing", "deleted"])
def test_object_marked_absent_after_reservation_is_not_copied(artifact, state):
    """Recheck the recorded state before starting a reserved transfer."""
    a = artifact
    reserve = storage_migration._reserve  # pylint: disable=protected-access

    def reserve_then_change_state(*args, **kwargs):
        result = reserve(*args, **kwargs)
        models.ObjectStorageObject.objects.filter(pk=a.obj.pk).update(state=state)
        return result

    with patch.object(
        storage_migration, "_reserve", side_effect=reserve_then_change_state
    ):
        assert "deferred=1" in run(a.obj)
    a.source_client.get_object.assert_not_called()
    a.obj.refresh_from_db()
    assert a.obj.state == state
    assert a.obj.storage_bucket_name == a.source_bucket


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


@pytest.mark.parametrize(
    ("field", "hex_digest"),
    [
        (
            "ChecksumSHA256",
            "15e2b0d3c33891ebb0f1ef609ec419420c20e320ce94c65fbc8c3312448eb225",
        ),
        ("ChecksumSHA1", "f7c3bc1d808e04732adf679965ccc34ca7ae3441"),
        ("ChecksumCRC32", "cbf43926"),
        ("ChecksumCRC32C", "e3069283"),
        ("ChecksumCRC64NVME", "ae8b14860a799888"),
    ],
)
def test_head_full_object_checksum_skips_download(
    artifact, monkeypatch, field, hex_digest
):
    """A matching HEAD checksum is enough even when it uses a different algorithm."""
    a = artifact
    content = b"123456789"
    a.copies[a.source_bucket, a.obj.key] = content
    publish_object(a.obj, content=content)
    monkeypatch.setattr(storage_migration, "CHUNK_SIZE", 4)
    a.client.head_object.side_effect = None
    a.client.head_object.return_value = {
        "ContentLength": len(content),
        "ChecksumType": "FULL_OBJECT",
        field: base64.b64encode(bytes.fromhex(hex_digest)).decode("ascii"),
    }

    assert "migrated=1" in run(a.obj)

    a.client.head_object.assert_called_once_with(
        Bucket="destination", Key=a.obj.key, ChecksumMode="ENABLED"
    )
    a.client.get_object.assert_not_called()
    checksum = a.obj.checksum_value
    a.obj.refresh_from_db()
    assert a.obj.checksum_value == checksum
    assert a.obj.checksum_algorithm == "SHA256"


@pytest.mark.parametrize("checksum_type", ["COMPOSITE", None])
def test_head_checksum_with_unclear_full_object_semantics_reads_destination(
    artifact, checksum_type
):
    """A checksum of unknown or composite type requires a full-content read."""
    a = artifact
    a.client.head_object.side_effect = None
    a.client.head_object.return_value = {
        "ContentLength": len(b"source bytes"),
        "ChecksumSHA256": "incomparable",
    }
    if checksum_type:
        a.client.head_object.return_value["ChecksumType"] = checksum_type

    assert "migrated=1" in run(a.obj)
    a.client.get_object.assert_called_once_with(Bucket="destination", Key=a.obj.key)


def test_head_unsupported_checksum_mode_reads_destination(artifact):
    """Providers that reject checksum mode can still use the full readback."""
    a = artifact
    a.client.head_object.side_effect = [
        ClientError({"Error": {"Code": "NotImplemented"}}, "HeadObject"),
        {"ContentLength": len(b"source bytes")},
    ]

    assert "migrated=1" in run(a.obj)
    a.client.get_object.assert_called_once_with(Bucket="destination", Key=a.obj.key)


def test_aligned_dry_run_loads_file_and_creator_together(django_assert_num_queries):
    """The routing check reuses the owning file read used for eligibility."""
    file = factories.FileFactory(update_upload_state="ready")
    obj = file.original_object
    publish_object(obj, content=b"source bytes")

    with django_assert_num_queries(1):
        assert migrate_object(obj.pk, dry_run=True) == "aligned"


def test_dry_run_batches_sources_and_destinations(artifact, django_assert_num_queries):
    """A full batch uses two reads even with retained and conflicting locations."""
    a = artifact
    now = timezone.now()
    sources = models.ObjectStorageObject.objects.bulk_create(
        models.ObjectStorageObject(
            file=a.file,
            file_identifier=a.file.pk,
            kind="summary",
            key=f"summary-{index}",
            storage_bucket_name=a.source_bucket,
            state="available",
            published_at=now,
        )
        for index in range(100)
    )
    held, reusable, conflict = sources[:3]
    for obj, deadline, authoritative_id in (
        (held, now + timedelta(hours=1), held.pk),
        (reusable, now - timedelta(hours=1), reusable.pk),
        (conflict, None, a.obj.pk),
    ):
        models.ObjectStorageObject.objects.create(
            file_identifier=a.file.pk,
            kind=obj.kind,
            key=obj.key,
            storage_bucket_name="destination",
            state="deleting",
            checksum_source="migration",
            etag=str(authoritative_id),
            published_at=now,
            metadata_checked_at=deadline,
        )

    stdout, stderr = StringIO(), StringIO()
    with django_assert_num_queries(2), pytest.raises(CommandError, match="1 storage"):
        call_command(
            "migrate_storage_objects",
            objects=[str(obj.pk) for obj in sources],
            dry_run=True,
            limit=100,
            stdout=stdout,
            stderr=stderr,
        )

    assert "aligned=0, migrated=98, deferred=1, failed=1" in stdout.getvalue()
    assert f"Last examined PK: {max(obj.pk for obj in sources)}" in stdout.getvalue()
    assert stderr.getvalue() == f"Failed objects: {conflict.pk} (ValueError)\n"


@pytest.mark.parametrize(
    "head_metadata",
    [
        {},
        {"ChecksumType": "FULL_OBJECT", "ChecksumSHA256": "mismatched"},
        {"ContentLength": 0},
    ],
)
def test_checksum_failure_leaves_source_authoritative(artifact, head_metadata):
    """A corrupted destination never becomes the authoritative location."""
    a = artifact
    a.client.upload_file.side_effect = lambda content, bucket, key, **kw: (
        a.copies.update({(bucket, key): b"broken bytes"})
    )
    head = a.client.head_object.side_effect
    a.client.head_object.side_effect = lambda **params: {
        **head(**params),
        **head_metadata,
    }
    with pytest.raises(CommandError):
        run(a.obj, stderr=StringIO())
    assert a.client.get_object.call_count == (0 if head_metadata else 1)
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
        assert (
            stderr.getvalue() == f"Failed objects: {a.obj.pk} (ObjectIntegrityError)\n"
        )
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
            original_file_data_delete_at=timezone.now() - timedelta(minutes=1),
            original_file_data_delete_at_with_grace_period=timezone.now(),
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
    assert "deferred=1" in run(audio.output_object, dry_run=True)
    assert "deferred=1" in run(audio.output_object)


def test_expiry_during_transfer_prevents_cutover(artifact):
    """A transfer cannot republish original data after its deadline."""
    a = artifact
    upload = a.client.upload_file.side_effect

    def expire(*args, **kwargs):
        upload(*args, **kwargs)
        models.File.objects.filter(pk=a.file.pk).update(
            original_file_data_delete_at=timezone.now() - timedelta(minutes=1),
            original_file_data_delete_at_with_grace_period=timezone.now(),
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


def test_destination_references_are_rechecked_after_reservation(artifact, monkeypatch):
    """A destination referenced after reservation fails before storage I/O."""
    a = artifact
    job = factories.AiFileJobFactory(file=a.file)
    reserve = storage_migration._reserve  # pylint: disable=protected-access

    def reserve_and_reference(obj_id, **kwargs):
        result, destination_id = reserve(obj_id, **kwargs)
        models.AiFileJob.objects.filter(pk=job.pk).update(
            result_object_id=destination_id
        )
        return result, destination_id

    monkeypatch.setattr(storage_migration, "_reserve", reserve_and_reference)
    with pytest.raises(CommandError, match="1 storage object"):
        run(a.obj, stderr=StringIO())
    a.source_client.get_object.assert_not_called()
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
    """Integration: actual S3 clients, bucket credentials, and verified upload."""
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("phase", ["reservation", "transfer"])
def test_command_skips_locked_object_and_migrates_next(artifact, monkeypatch, phase):
    """A lock in either transaction lets a worker continue to another object."""
    a = artifact
    other_file = factories.FileFactory(update_upload_state="ready")
    other = other_file.original_object
    a.copies[a.source_bucket, other.key] = b"other bytes"
    publish_object(other, content=b"other bytes")
    locked, available = sorted([a.obj, other], key=lambda obj: obj.pk)
    ready, resume = Event(), Event()
    reserve = storage_migration._reserve  # pylint: disable=protected-access

    def reserve_with_pause(obj_id, **kwargs):
        if obj_id != locked.pk:
            return reserve(obj_id, **kwargs)
        result = reserve(obj_id, **kwargs) if phase == "transfer" else None
        ready.set()
        assert resume.wait(10)
        return result if result is not None else reserve(obj_id, **kwargs)

    def migrate():
        try:
            output = StringIO()
            call_command(
                "migrate_storage_objects",
                objects=[str(locked.pk), str(available.pk)],
                source_bucket=a.source_bucket,
                stdout=output,
            )
            return output.getvalue()
        finally:
            close_old_connections()

    monkeypatch.setattr(storage_migration, "_reserve", reserve_with_pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(migrate)
        assert ready.wait(10)
        with transaction.atomic():
            models.ObjectStorageObject.objects.select_for_update().get(pk=locked.pk)
            resume.set()
            output = worker.result(timeout=10)

    assert "migrated=1" in output
    assert "skipped=1" in output
    locked.refresh_from_db()
    assert locked.storage_bucket_name == a.source_bucket
    monkeypatch.setattr(storage_migration, "_reserve", reserve)
    assert "migrated=1" in run(locked, source_bucket=a.source_bucket)


def test_source_bucket_rechecked_after_reservation(artifact, monkeypatch):
    """An object that leaves the selected source must not be copied from elsewhere."""
    a = artifact
    reserve = storage_migration._reserve  # pylint: disable=protected-access

    def reserve_and_move(obj_id, **kwargs):
        result = reserve(obj_id, **kwargs)
        models.ObjectStorageObject.objects.filter(pk=obj_id).update(
            storage_bucket_name="another-bucket"
        )
        return result

    monkeypatch.setattr(storage_migration, "_reserve", reserve_and_move)
    assert "skipped=1" in run(a.obj, source_bucket=a.source_bucket)
    a.source_client.get_object.assert_not_called()
    a.client.upload_file.assert_not_called()


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
    first, next_run, exhausted = StringIO(), StringIO(), StringIO()
    call_command("migrate_storage_objects", stdout=first, **options)
    assert "deferred=1" in first.getvalue()
    assert f"Last examined PK: {ids[0]}" in first.getvalue()
    call_command(
        "migrate_storage_objects", start_after=ids[0], stdout=next_run, **options
    )
    assert f"Last examined PK: {ids[1]}" in next_run.getvalue()
    assert str(ids[0]) not in next_run.getvalue()
    call_command(
        "migrate_storage_objects", start_after=ids[1], stdout=exhausted, **options
    )
    assert exhausted.getvalue().splitlines() == [
        "Dry run (would migrate): aligned=0, migrated=0, deferred=0, failed=0, skipped=0",
        "Last examined PK: none",
    ]


def test_command_reports_current_state_at_most_every_twenty_seconds(artifact):
    """Progress snapshots are time based and include counts and the current PK."""
    obj = artifact.obj
    second = models.ObjectStorageObject.objects.get(
        pk=obj.file.temporary_upload_object_id
    )
    output = StringIO()
    with patch.object(
        migrate_storage_objects.time, "monotonic", side_effect=[0, 19, 20]
    ):
        call_command(
            "migrate_storage_objects",
            objects=[str(obj.pk), str(second.pk)],
            dry_run=True,
            stdout=output,
        )
    lines = output.getvalue().splitlines()
    progress = [line for line in lines if line.startswith("Progress:")]
    assert len(progress) == 1
    assert progress[0].startswith("Progress: processed=2/1000, ")
    assert f"last_pk={max(obj.pk, second.pk)}" in progress[0]
    assert not any(": migrated" in line or ": deferred" in line for line in lines)


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
