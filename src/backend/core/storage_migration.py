"""Move immutable tracked artifacts without changing their owning file's policy."""

from collections import defaultdict
from datetime import timedelta
from tempfile import NamedTemporaryFile
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Value
from django.db.models.lookups import In
from django.utils import timezone

from boto3.s3.transfer import TransferConfig
from botocore.httpchecksum import (
    CrtCrc32cChecksum,
    CrtCrc32Checksum,
    CrtCrc64NvmeChecksum,
    Sha1Checksum,
    Sha256Checksum,
)

from core.configuration import get_profile_for_email
from core.models import (
    AiFileJob,
    AudioJob,
    File,
    FileLifecycleStateChoices,
    FileUploadStateChoices,
    ObjectStorageObject,
)
from core.object_storage import (
    CHECKSUM_FIELDS,
    ObjectIntegrityError,
    head_s3_object,
    metadata_values,
)
from core.storage import get_bucket_configuration_for_object, get_storage_for_object

# Cleanup obligations use existing fields, never owner references. For these rows
# metadata_checked_at is the cleanup deadline; published_at distinguishes a retained
# source from a possibly partial destination. They are not migration history.
CLEANUP_SOURCE = "migration"
CONTENT_METADATA = (
    "ContentType",
    "ContentEncoding",
    "ContentLanguage",
    "ContentDisposition",
    "CacheControl",
    "Expires",
    "Metadata",
)
CHUNK_SIZE = 10 * 1024 * 1024
# S3 accepts single PUT requests and multipart parts of up to 5 GiB.
MIN_MULTIPART_PART_SIZE = 5 * 1024**2
MAX_PART_SIZE = 5 * 1024**3

# CRC baselines use the AWS CRT's native implementations (boto3[crt]); a
# pure-Python CRC would hold the object lock for minutes on large files.
BASELINE_CHECKSUMS = {
    "SHA256": Sha256Checksum,
    "SHA1": Sha1Checksum,
    "CRC32": CrtCrc32Checksum,
    "CRC32C": CrtCrc32cChecksum,
    "CRC64NVME": CrtCrc64NvmeChecksum,
}
ROUTING_FILE_FIELDS = (
    "creator__email",
    "upload_state",
    "hard_deleted_at",
    "lifecycle_state",
    "file_auto_hard_delete_at",
    "trashbin_purge_at",
    "original_file_data_delete_at_with_grace_period",
)
RECORD_ONLY_STATES = {
    ObjectStorageObject.State.MISSING,
    ObjectStorageObject.State.DELETED,
}
ORIGINAL_DATA_KINDS = {
    ObjectStorageObject.Kind.ORIGINAL,
    ObjectStorageObject.Kind.TEMPORARY,
    ObjectStorageObject.Kind.AUDIO,
}


def _eligible_source(obj):
    if obj.file_id is None:
        return False
    if obj.state in RECORD_ONLY_STATES:
        return True
    return (
        obj.state == obj.State.AVAILABLE
        and obj.kind != obj.Kind.TEMPORARY
        and obj.published_at is not None
        and (
            obj.checksum_type != "FULL_OBJECT"
            or (
                obj.checksum_algorithm in BASELINE_CHECKSUMS
                and bool(obj.checksum_value)
            )
        )
    )


def _active_audio_upload(obj_id, now):
    return Exists(AudioJob.objects.filter(output_object_id=obj_id, expires_at__gt=now))


def _original_data_was_deleted(obj, file):
    return (
        file.lifecycle_state == FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
        and obj.kind in ORIGINAL_DATA_KINDS
    )


def _should_mark_deleted(obj, file):
    return obj.state == obj.State.MISSING and _original_data_was_deleted(obj, file)


def _eligible_owner(obj, file, now):
    if file is None:
        return False
    if obj.kind == obj.Kind.TEMPORARY:
        return _original_data_was_deleted(obj, file)
    if obj.state == obj.State.DELETED or _should_mark_deleted(obj, file):
        # Retention may have expired before the artifact was deleted.
        return True
    if file.upload_state != FileUploadStateChoices.READY or file.hard_deleted_at:
        return False
    deadlines = [file.file_auto_hard_delete_at, file.trashbin_purge_at]
    if obj.kind in {obj.Kind.ORIGINAL, obj.Kind.AUDIO}:
        if file.lifecycle_state not in {
            FileLifecycleStateChoices.ACTIVE,
            FileLifecycleStateChoices.PENDING_ORIGINAL_DATA_DELETION,
        }:
            return False
        if obj.state == obj.State.AVAILABLE:
            deadlines.append(file.original_file_data_delete_at_with_grace_period)
    return file.lifecycle_state != "pending_auto_hard_delete" and not any(
        deadline and deadline <= now for deadline in deadlines
    )


def _routing_file(obj, now, *, destination_id=None):
    """Read current lifecycle, routing, and upload inputs without a file lock."""
    files = File.objects.select_related("creator").only(*ROUTING_FILE_FIELDS)
    files = files.annotate(
        has_active_upload=(
            _active_audio_upload(obj.pk, now)
            if obj.kind == obj.Kind.AUDIO
            else Value(False)
        )
    )
    if destination_id is not None:
        files = files.annotate(
            has_destination_references=_destination_references(destination_id)
        )
    return files.filter(pk=obj.file_id).first()


def _eligible_file(obj, *, destination_id=None):
    """Recheck eligibility immediately before and after copying bytes."""
    if not _eligible_source(obj):
        return None
    now = timezone.now()
    file = _routing_file(obj, now, destination_id=destination_id)
    if file and not file.has_active_upload and _eligible_owner(obj, file, now):
        return file
    return None


def expected_bucket(file):
    """Use the creator's current routing configuration, not the file snapshot."""
    return get_profile_for_email(
        file.creator.email if file.creator_id else None
    ).storage_bucket_name


def _inspect_source(obj, file, now, *, has_active_upload):
    """Recognize alignment before checking whether an object can move."""
    if file is None:
        return "deferred", None
    bucket = expected_bucket(file)
    if bucket == obj.storage_bucket_name and not _should_mark_deleted(obj, file):
        return "aligned", bucket
    if (
        has_active_upload
        or not _eligible_source(obj)
        or not _eligible_owner(obj, file, now)
    ):
        return "deferred", None
    return "migrated", bucket


def _retaining_file(file_identifier, kind, now):
    """Find an owner whose retention rules still protect a copy of this kind."""
    original_data = Q(
        In(kind, (ObjectStorageObject.Kind.ORIGINAL, ObjectStorageObject.Kind.AUDIO))
    )
    return (
        File.objects.filter(
            pk=file_identifier,
            hard_deleted_at__isnull=True,
            file_auto_hard_delete_at_with_grace_period__gt=now,
        )
        .exclude(trashbin_purge_at_with_grace_period__lte=now)
        .filter(
            ~original_data
            | (
                Q(original_file_data_delete_at_with_grace_period__gt=now)
                & ~Q(lifecycle_state=FileLifecycleStateChoices.ORIGINAL_DATA_DELETED)
            )
        )
    )


def _cleanup_due_condition(now):
    return (
        ~Q(checksum_source=CLEANUP_SOURCE)
        | Q(published_at__isnull=True)
        | Q(metadata_checked_at__lte=now)
        | ~Exists(_retaining_file(OuterRef("file_identifier"), OuterRef("kind"), now))
    )


def cleanup_candidates(now):
    """Select due cleanup rows in SQL using the persisted owning-file identifier."""
    return ObjectStorageObject.objects.filter(
        _cleanup_due_condition(now),
        state=ObjectStorageObject.State.DELETING,
    )


def cleanup_due(obj):
    """Retained URLs never extend persisted retention or explicit deletion intent."""
    if obj.checksum_source != CLEANUP_SOURCE or obj.published_at is None:
        return True
    now = timezone.now()
    if obj.metadata_checked_at is not None and obj.metadata_checked_at <= now:
        return True
    return not _retaining_file(obj.file_identifier, Value(obj.kind), now).exists()


def retained_copy(file, bucket, key, kinds):
    """Find a migrated-away source still serving URLs that name its old bucket.

    Only a retained source whose authoritative object is still live qualifies; the
    caller keeps enforcing the file's own access and data retention rules.
    """
    copy = ObjectStorageObject.objects.filter(
        file_identifier=file.pk,
        file__isnull=True,
        checksum_source=CLEANUP_SOURCE,
        storage_bucket_name=bucket,
        key=key,
        kind__in=kinds,
        state=ObjectStorageObject.State.DELETING,
        published_at__isnull=False,
    ).first()
    if copy is None or cleanup_due(copy):
        return None
    try:
        authoritative_id = UUID(copy.etag)
    except ValueError:
        return None
    is_live = (
        file.storage_objects.filter(pk=authoritative_id, kind=copy.kind)
        .exclude(
            state__in=[
                ObjectStorageObject.State.DELETING,
                ObjectStorageObject.State.DELETED,
            ]
        )
        .exists()
    )
    return copy if is_live else None


def _destination_references(destination_id):
    return (
        Exists(
            File.objects.filter(
                Q(original_object_id=destination_id)
                | Q(temporary_upload_object_id=destination_id)
            )
        )
        | Exists(AudioJob.objects.filter(output_object_id=destination_id))
        | Exists(AiFileJob.objects.filter(result_object_id=destination_id))
    )


def _validate_destination(destination, obj, *, has_references=None):
    """Only a detached cleanup obligation for this artifact can be reused."""
    if not (
        destination.checksum_source == CLEANUP_SOURCE
        and destination.etag == str(obj.pk)
        and destination.file_id is None
        and destination.file_identifier == obj.file_identifier
        and destination.kind == obj.kind
        and destination.state in {obj.State.DELETING, obj.State.DELETED}
    ):
        raise ValueError("Destination belongs to another tracked artifact")
    if has_references is None:
        has_references = ObjectStorageObject.objects.filter(
            _destination_references(destination.pk), pk=destination.pk
        ).exists()
    if has_references:
        raise ValueError("Destination belongs to another tracked artifact")


def _destination_held(destination):
    """Keep a prior source intact while its issued URLs are still retained."""
    return destination.state == destination.State.DELETING and not cleanup_due(
        destination
    )


def _move_object_record(obj, bucket, *, mark_deleted):
    """Move only the tracked location while the source row is locked."""
    if bucket != obj.storage_bucket_name:
        destination = (
            ObjectStorageObject.objects.select_for_update()
            .filter(storage_bucket_name=bucket, key=obj.key)
            .first()
        )
        if destination is not None:
            _validate_destination(destination, obj)
            if destination.state == destination.State.DELETING:
                return "deferred"
            destination.delete()
    elif not mark_deleted:
        return "aligned"
    ObjectStorageObject.objects.filter(pk=obj.pk).update(
        storage_bucket_name=bucket,
        state=obj.State.DELETED if mark_deleted else obj.state,
        updated_at=timezone.now(),
    )
    return "migrated"


def _source_candidate(obj_id, source_bucket):
    """Find a candidate if it is still in the requested source bucket."""
    objects = ObjectStorageObject.objects.filter(pk=obj_id)
    if source_bucket is not None:
        objects = objects.filter(storage_bucket_name=source_bucket)
    return objects


def _reserve(obj_id, *, source_bucket):
    """Move a record alone or commit a cleanup obligation before copying bytes."""
    with transaction.atomic():
        obj = (
            _source_candidate(obj_id, source_bucket)
            .select_for_update(skip_locked=True)
            .first()
        )
        if obj is None:
            return "skipped", None
        now = timezone.now()
        file = _routing_file(obj, now) if obj.file_id else None
        outcome, bucket = _inspect_source(
            obj, file, now, has_active_upload=file and file.has_active_upload
        )
        if outcome != "migrated":
            return outcome, None
        if obj.state in RECORD_ONLY_STATES:
            mark_deleted = _should_mark_deleted(obj, file)
            return _move_object_record(obj, bucket, mark_deleted=mark_deleted), None
        destination, created = (
            ObjectStorageObject.objects.select_for_update().get_or_create(
                storage_bucket_name=bucket,
                key=obj.key,
                defaults={
                    "file_identifier": obj.file_identifier,
                    "kind": obj.kind,
                    "state": obj.State.DELETING,
                    "checksum_source": CLEANUP_SOURCE,
                    "etag": str(obj.pk),
                },
            )
        )
        if not created:
            _validate_destination(destination, obj)
            if _destination_held(destination):
                return "deferred", None
            # A concurrent cleanup may have finished since an earlier attempt. This
            # committed reset makes another interrupted write discoverable again.
            ObjectStorageObject.objects.filter(pk=destination.pk).update(
                state=obj.State.DELETING,
                published_at=None,
                metadata_checked_at=None,
                deleted_at=None,
                updated_at=timezone.now(),
            )
        return "reserved", destination.pk


def _read(client, obj, target=None, *, baseline=None):
    """Hash every byte, optionally spooling it to bounded-memory temporary disk."""
    response = client.get_object(Bucket=obj.storage_bucket_name, Key=obj.key)
    digest = Sha256Checksum()
    size = 0
    body = response["Body"]
    try:
        while chunk := body.read(CHUNK_SIZE):
            digest.update(chunk)
            if baseline is not None:
                baseline.update(chunk)
            size += len(chunk)
            if target is not None:
                target.write(chunk)
    finally:
        body.close()
    if size != response["ContentLength"]:
        raise ObjectIntegrityError("Incomplete storage read")
    return response, size, digest.b64digest()


def _upload(client, destination, content, source_metadata, digest):
    """Upload the file and verify the destination's size and checksum."""
    bucket, key = destination.storage_bucket_name, destination.key
    size = source_metadata["ContentLength"]
    extra = {
        key: source_metadata[key] for key in CONTENT_METADATA if key in source_metadata
    }
    acl = get_bucket_configuration_for_object(destination).upload_acl
    if acl is not None:
        extra["ACL"] = acl
    # Objects up to FILE_UPLOAD_MAX_SIZE take a single PUT; only objects above
    # it (or above S3's single-request limit) use multipart, in parts that size.
    part_size = min(
        MAX_PART_SIZE,
        max(MIN_MULTIPART_PART_SIZE, settings.FILE_UPLOAD_MAX_SIZE),
    )
    # Upload by filename so Boto3 can stream the body directly from disk.
    client.upload_file(
        content.name,
        bucket,
        key,
        ExtraArgs=extra,
        Config=TransferConfig(
            multipart_threshold=part_size + 1,
            multipart_chunksize=part_size,
            # Never let an installed CRT swap in a client that ignores this config.
            preferred_transfer_client="classic",
        ),
    )
    return _verify_destination(client, destination, content, size, digest)


def _verify_destination(client, destination, content, size, digest):
    """Compare a supported full-object checksum or fall back to reading the copy."""
    head = head_s3_object(client, destination)
    if head is None or head["ContentLength"] != size:
        raise ObjectIntegrityError("Destination missing or size mismatch")

    if head.get("ChecksumType") == "FULL_OBJECT":
        for field, algorithm in CHECKSUM_FIELDS:
            if not head.get(field):
                continue
            expected = digest
            if algorithm != "SHA256":
                checksum = BASELINE_CHECKSUMS[algorithm]()
                content.seek(0)
                while chunk := content.read(CHUNK_SIZE):
                    checksum.update(chunk)
                expected = checksum.b64digest()
            if head[field] != expected:
                raise ObjectIntegrityError("Destination full-content checksum mismatch")
            return head

    response, copied_size, copied_digest = _read(client, destination)
    if (copied_size, copied_digest) != (size, digest):
        raise ObjectIntegrityError("Destination full-content checksum or size mismatch")
    return response


def _transfer(obj, destination):
    """Use each bucket's own credentials and verify the copied bytes."""
    source_client = get_storage_for_object(obj).connection.meta.client
    storage = get_storage_for_object(destination)
    client = storage.connection.meta.client
    baseline = None
    if obj.checksum_type == "FULL_OBJECT" and obj.checksum_algorithm != "SHA256":
        baseline = BASELINE_CHECKSUMS[obj.checksum_algorithm]()
    with NamedTemporaryFile(delete_on_close=False) as content:
        response, size, digest = _read(source_client, obj, content, baseline=baseline)
        if obj.size is not None and obj.size != size:
            raise ObjectIntegrityError("Source size differs from published baseline")
        if obj.checksum_type == "FULL_OBJECT":
            observed = digest if baseline is None else baseline.b64digest()
            if obj.checksum_value != observed:
                raise ObjectIntegrityError(
                    "Source checksum differs from published baseline"
                )
        content.flush()
        head = _upload(client, destination, content, response, digest)
    values = metadata_values(head)
    values.update(
        checksum_algorithm="SHA256",
        checksum_value=digest,
        checksum_type="FULL_OBJECT",
        checksum_source="application",
    )
    return values


def inspect_objects(objects):
    """Plan an ordered batch with one source read and up to one destination read."""
    now = timezone.now()
    sources = (
        objects.select_related("file__creator")
        .only(
            "state",
            "published_at",
            "kind",
            "file_identifier",
            "checksum_type",
            "checksum_algorithm",
            "checksum_value",
            "storage_bucket_name",
            "key",
            *(f"file__{field}" for field in ROUTING_FILE_FIELDS),
        )
        .annotate(
            has_active_upload=Q(kind=ObjectStorageObject.Kind.AUDIO)
            & _active_audio_upload(OuterRef("pk"), now),
        )
    )
    results = {}
    targets = []
    keys_by_bucket = defaultdict(set)
    for obj in sources:
        try:
            outcome, bucket = _inspect_source(
                obj, obj.file, now, has_active_upload=obj.has_active_upload
            )
        except Exception as exc:  # noqa: BLE001 # pylint: disable=broad-exception-caught
            results[obj.pk] = exc
            continue
        results[obj.pk] = outcome
        if outcome != "migrated" or bucket == obj.storage_bucket_name:
            continue
        targets.append((obj, bucket))
        keys_by_bucket[bucket].add(obj.key)

    if not targets:
        return results
    locations = Q()
    for bucket, keys in keys_by_bucket.items():
        locations |= Q(storage_bucket_name=bucket, key__in=keys)
    destinations = {
        (obj.storage_bucket_name, obj.key): obj
        for obj in ObjectStorageObject.objects.filter(locations).annotate(
            has_references=_destination_references(OuterRef("pk")),
            cleanup_is_due=_cleanup_due_condition(now),
        )
    }
    for obj, bucket in targets:
        destination = destinations.get((bucket, obj.key))
        if destination is None:
            continue
        try:
            _validate_destination(
                destination, obj, has_references=destination.has_references
            )
        except ValueError as exc:
            results[obj.pk] = exc
            continue
        if destination.state == destination.State.DELETING and (
            obj.state in RECORD_ONLY_STATES or not destination.cleanup_is_due
        ):
            results[obj.pk] = "deferred"
    return results


def inspect_object(obj_id, *, source_bucket=None):
    """Plan a transfer using only database reads."""
    results = inspect_objects(_source_candidate(obj_id, source_bucket))
    if not results:
        if source_bucket is not None:
            return "skipped"
        raise ObjectStorageObject.DoesNotExist
    result = next(iter(results.values()))
    if isinstance(result, Exception):
        raise result
    return result


def _move_reserved_object(obj_id, destination_id, source_bucket):
    """Keep the authoritative ID and source location until verified cutover commits."""
    with transaction.atomic():
        obj = (
            _source_candidate(obj_id, source_bucket)
            .select_for_update(skip_locked=True)
            .first()
        )
        if obj is None:
            return "skipped"
        if obj.state != obj.State.AVAILABLE:
            return "deferred"
        destination = (
            ObjectStorageObject.objects.select_for_update()
            .filter(
                pk=destination_id,
                state=ObjectStorageObject.State.DELETING,
            )
            .first()
        )
        if destination is None:
            return "deferred"
        file = _eligible_file(obj, destination_id=destination.pk)
        if file is None or expected_bucket(file) != destination.storage_bucket_name:
            return "deferred"
        _validate_destination(
            destination, obj, has_references=file.has_destination_references
        )
        values = _transfer(obj, destination)
        file = _eligible_file(obj)
        if file is None or expected_bucket(file) != destination.storage_bucket_name:
            return "deferred"
        old_bucket = obj.storage_bucket_name
        # Release the destination's unique location, retaining the authoritative ID.
        destination.delete()
        ObjectStorageObject.objects.filter(pk=obj.pk).update(
            storage_bucket_name=destination.storage_bucket_name,
            updated_at=timezone.now(),
            **values,
        )
        ObjectStorageObject.objects.create(
            file_identifier=obj.file_identifier,
            kind=obj.kind,
            storage_bucket_name=old_bucket,
            key=obj.key,
            state=obj.State.DELETING,
            checksum_source=CLEANUP_SOURCE,
            etag=str(obj.pk),
            published_at=obj.published_at,
            metadata_checked_at=timezone.now()
            + timedelta(
                seconds=max(
                    86400,
                    settings.AUDIO_JOB_TIMEOUT_SECONDS,
                    getattr(settings, "AWS_QUERYSTRING_EXPIRE", 3600),
                )
            ),
        )
    return "migrated"


def migrate_object(obj_id, *, dry_run=False, source_bucket=None):
    """Commit the cleanup obligation before transferring an object."""
    if dry_run:
        return inspect_object(obj_id, source_bucket=source_bucket)
    result, destination_id = _reserve(obj_id, source_bucket=source_bucket)
    if result != "reserved":
        return result
    return _move_reserved_object(obj_id, destination_id, source_bucket)
