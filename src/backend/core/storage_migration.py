"""Move immutable tracked artifacts without changing their owning file's policy."""

from datetime import timedelta
from functools import lru_cache, partial
from tempfile import NamedTemporaryFile
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, Q
from django.utils import timezone

from boto3.s3.transfer import TransferConfig
from botocore.httpchecksum import (
    BaseChecksum,
    Crc32Checksum,
    Sha1Checksum,
    Sha256Checksum,
)

from core.configuration import get_profile_for_email
from core.models import (
    AiFileJob,
    AudioJob,
    File,
    FileUploadStateChoices,
    ObjectStorageObject,
)
from core.object_storage import ObjectIntegrityError, metadata_values
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


@lru_cache(maxsize=2)
def _crc_table(polynomial):
    """Build the lookup table for a reflected CRC polynomial."""
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ (polynomial if value & 1 else 0)
        table.append(value)
    return tuple(table)


class _ReflectedChecksum(BaseChecksum):
    """Compute CRC32C or CRC64/NVME in Python."""

    def __init__(self, polynomial, width):
        self.table = _crc_table(polynomial)
        self.width = width
        self.mask = (1 << (width * 8)) - 1
        self.value = self.mask

    def update(self, chunk):
        value, table = self.value, self.table
        for byte in chunk:
            value = (value >> 8) ^ table[(value ^ byte) & 0xFF]
        self.value = value

    def digest(self):
        return (self.value ^ self.mask).to_bytes(self.width, "big")


BASELINE_CHECKSUMS = {
    "SHA256": Sha256Checksum,
    "SHA1": Sha1Checksum,
    "CRC32": Crc32Checksum,
    "CRC32C": partial(_ReflectedChecksum, 0x82F63B78, 4),
    "CRC64NVME": partial(_ReflectedChecksum, 0x9A6C9329AC4BC9B5, 8),
}


def _eligible_file(obj):
    """Read current lifecycle and routing inputs in one query without a file lock."""
    if (
        obj.state != obj.State.AVAILABLE
        or obj.published_at is None
        or obj.kind == obj.Kind.TEMPORARY
        or not obj.file_id
    ):
        return None
    if obj.checksum_type == "FULL_OBJECT" and (
        obj.checksum_algorithm not in BASELINE_CHECKSUMS or not obj.checksum_value
    ):
        return None
    files = File.objects.select_related("creator")
    if obj.kind == obj.Kind.AUDIO:
        files = files.filter(
            ~Exists(
                AudioJob.objects.filter(
                    output_object_id=obj.pk, expires_at__gt=timezone.now()
                )
            )
        )
    file = files.filter(pk=obj.file_id).first()
    if (
        file is None
        or file.upload_state != FileUploadStateChoices.READY
        or file.hard_deleted_at
    ):
        return None
    deadlines = [file.file_auto_hard_delete_at, file.trashbin_purge_at]
    if obj.kind in {obj.Kind.ORIGINAL, obj.Kind.AUDIO}:
        deadlines.append(file.original_file_data_delete_at)
        if file.lifecycle_state != "active":
            return None
    now = timezone.now()
    if file.lifecycle_state == "pending_auto_hard_delete" or any(
        deadline and deadline <= now for deadline in deadlines
    ):
        return None
    return file


def expected_bucket(file):
    """Use the creator's current routing configuration, not the file snapshot."""
    return get_profile_for_email(
        file.creator.email if file.creator_id else None
    ).storage_bucket_name


def cleanup_due(obj):
    """Retained URLs never extend persisted retention or explicit deletion intent."""
    if obj.checksum_source != CLEANUP_SOURCE or obj.published_at is None:
        return True
    now = timezone.now()
    file = File.objects.filter(pk=obj.file_identifier).first()
    if file is None or file.hard_deleted_at:
        return True
    deadlines = [
        obj.metadata_checked_at,
        file.file_auto_hard_delete_at_with_grace_period,
        file.trashbin_purge_at_with_grace_period,
    ]
    if obj.kind in {obj.Kind.ORIGINAL, obj.Kind.AUDIO}:
        deadlines.append(file.original_file_data_delete_at_with_grace_period)
        if file.lifecycle_state == "original_data_deleted":
            return True
    return any(deadline and deadline <= now for deadline in deadlines)


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


def _validate_destination(destination, obj):
    """Only a detached cleanup obligation for this artifact can be reused."""
    if not (
        destination.checksum_source == CLEANUP_SOURCE
        and destination.etag == str(obj.pk)
        and destination.file_id is None
        and destination.file_identifier == obj.file_identifier
        and destination.kind == obj.kind
        and destination.state in {obj.State.DELETING, obj.State.DELETED}
    ) or (
        ObjectStorageObject.objects.filter(pk=destination.pk)
        .filter(
            Exists(
                File.objects.filter(
                    Q(original_object=destination)
                    | Q(temporary_upload_object=destination)
                )
            )
            | Exists(AudioJob.objects.filter(output_object=destination))
            | Exists(AiFileJob.objects.filter(result_object=destination))
        )
        .exists()
    ):
        raise ValueError("Destination belongs to another tracked artifact")


def _destination_held(destination):
    """Keep a prior source intact while its issued URLs are still retained."""
    return destination.state == destination.State.DELETING and not cleanup_due(
        destination
    )


def _reserve(obj_id):
    """Commit a cleanup obligation BEFORE any external write can happen."""
    with transaction.atomic():
        obj = ObjectStorageObject.objects.select_for_update().get(pk=obj_id)
        file = _eligible_file(obj)
        if file is None:
            return "deferred", None
        bucket = expected_bucket(file)
        if bucket == obj.storage_bucket_name:
            return "aligned", None
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
        if created:
            return "reserved", destination.pk
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
        ),
    )
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


def inspect_object(obj_id):
    """Plan a transfer using only database reads."""
    obj = ObjectStorageObject.objects.get(pk=obj_id)
    file = _eligible_file(obj)
    if file is None:
        return "deferred"
    bucket = expected_bucket(file)
    if bucket == obj.storage_bucket_name:
        return "aligned"
    destination = ObjectStorageObject.objects.filter(
        storage_bucket_name=bucket, key=obj.key
    ).first()
    if destination is not None:
        _validate_destination(destination, obj)
        if _destination_held(destination):
            return "deferred"
    return "migrated"


def migrate_object(obj_id, *, dry_run=False):
    """Keep the authoritative ID and source location until verified cutover commits."""
    if dry_run:
        return inspect_object(obj_id)
    result, destination_id = _reserve(obj_id)
    if result != "reserved":
        return result
    with transaction.atomic():
        obj = ObjectStorageObject.objects.select_for_update().get(pk=obj_id)
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
        file = _eligible_file(obj)
        if file is None or expected_bucket(file) != destination.storage_bucket_name:
            return "deferred"
        _validate_destination(destination, obj)
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
