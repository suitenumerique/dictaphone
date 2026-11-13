"""Move immutable tracked artifacts without changing their owning file's policy."""

import base64
import hashlib
from datetime import timedelta
from tempfile import TemporaryFile

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.configuration import get_profile_for_email
from core.models import (
    AiFileJob,
    AudioJob,
    File,
    FileUploadStateChoices,
    ObjectStorageObject,
)
from core.object_storage import ObjectIntegrityError, metadata_values
from core.storage import get_storage_for_object

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


def eligible(obj):
    """Read current lifecycle state without locking the file or resnapshotting it."""
    if (
        obj.state != obj.State.AVAILABLE
        or obj.published_at is None
        or obj.kind == obj.Kind.TEMPORARY
        or not obj.file_id
    ):
        return False
    file = File.objects.filter(pk=obj.file_id).first()
    if (
        file is None
        or file.upload_state != FileUploadStateChoices.READY
        or file.hard_deleted_at
    ):
        return False
    now = timezone.now()
    deadlines = [file.file_auto_hard_delete_at, file.trashbin_purge_at]
    if obj.kind in {obj.Kind.ORIGINAL, obj.Kind.AUDIO}:
        deadlines.append(file.original_file_data_delete_at)
        if file.lifecycle_state != "active":
            return False
    if file.lifecycle_state == "pending_auto_hard_delete":
        return False
    if any(deadline and deadline <= now for deadline in deadlines):
        return False
    return not (
        obj.kind == obj.Kind.AUDIO
        and AudioJob.objects.filter(
            output_object_id=obj.pk,
            expires_at__gt=now,
        ).exists()
    )


def expected_bucket(obj):
    """Use the creator's current routing configuration, not the file snapshot."""
    file = File.objects.select_related("creator").get(pk=obj.file_id)
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
        File.objects.filter(
            Q(original_object=destination) | Q(temporary_upload_object=destination)
        ).exists()
        or AudioJob.objects.filter(output_object=destination).exists()
        or AiFileJob.objects.filter(result_object=destination).exists()
    ):
        raise ValueError("Destination belongs to another tracked artifact")


def _reserve(obj_id):
    """Commit a cleanup obligation BEFORE any external write can happen."""
    with transaction.atomic():
        obj = ObjectStorageObject.objects.select_for_update().get(pk=obj_id)
        if not eligible(obj):
            return "deferred", None
        bucket = expected_bucket(obj)
        if bucket == obj.storage_bucket_name:
            return "aligned", None
        destination, _ = ObjectStorageObject.objects.get_or_create(
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
        destination = ObjectStorageObject.objects.select_for_update().get(
            pk=destination.pk
        )
        _validate_destination(destination, obj)
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


def _read(client, obj, target=None):
    """Hash every byte, optionally spooling it to bounded-memory temporary disk."""
    response = client.get_object(Bucket=obj.storage_bucket_name, Key=obj.key)
    digest = hashlib.sha256()
    size = 0
    body = response["Body"]
    try:
        while chunk := body.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
            if target is not None:
                target.write(chunk)
    finally:
        body.close()
    if size != response["ContentLength"]:
        raise ObjectIntegrityError("Incomplete storage read")
    return response, size, base64.b64encode(digest.digest()).decode("ascii")


def _transfer(obj, destination):
    """Use each bucket's own credentials; verify a complete destination read-back."""
    source_client = get_storage_for_object(obj).connection.meta.client
    storage = get_storage_for_object(destination)
    client = storage.connection.meta.client
    with TemporaryFile() as content:
        response, size, digest = _read(source_client, obj, content)
        if obj.size is not None and obj.size != size:
            raise ObjectIntegrityError("Source size differs from published baseline")
        if (
            obj.checksum_algorithm == "SHA256"
            and obj.checksum_type == "FULL_OBJECT"
            and obj.checksum_value != digest
        ):
            raise ObjectIntegrityError(
                "Source checksum differs from published baseline"
            )
        content.seek(0)
        # Managed upload supports multipart objects and overwrites the exact key.
        extra = {key: response[key] for key in CONTENT_METADATA if key in response}
        client.upload_fileobj(
            content, destination.storage_bucket_name, destination.key, ExtraArgs=extra
        )
    head, copied_size, copied_digest = _read(client, destination)
    if (copied_size, copied_digest) != (size, digest):
        raise ObjectIntegrityError("Destination full-content checksum or size mismatch")
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
    if not eligible(obj):
        return "deferred"
    bucket = expected_bucket(obj)
    if bucket == obj.storage_bucket_name:
        return "aligned"
    destination = ObjectStorageObject.objects.filter(
        storage_bucket_name=bucket, key=obj.key
    ).first()
    if destination is not None:
        _validate_destination(destination, obj)
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
        if (
            destination is None
            or not eligible(obj)
            or expected_bucket(obj) != destination.storage_bucket_name
        ):
            return "deferred"
        _validate_destination(destination, obj)
        values = _transfer(obj, destination)
        if not eligible(obj) or expected_bucket(obj) != destination.storage_bucket_name:
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
