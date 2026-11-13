"""Register storage locations and observe metadata without downloading content."""

# Model save hooks import this service lazily after model loading.
# pylint: disable=cyclic-import

import base64
import hashlib
from os.path import splitext

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from botocore.exceptions import ClientError
from storages.backends.s3 import S3Storage

from core.configuration import get_profile_for_email
from core.models import ObjectStorageObject
from core.storage import get_storage_for_object

CHECKSUM_FIELDS = (
    ("ChecksumSHA256", "SHA256"),
    ("ChecksumSHA1", "SHA1"),
    ("ChecksumCRC64NVME", "CRC64NVME"),
    ("ChecksumCRC32C", "CRC32C"),
    ("ChecksumCRC32", "CRC32"),
)
ABSENT_CODES = {"404", "NoSuchKey", "NotFound"}


class ObjectIntegrityError(ValueError):
    """A metadata observation conflicts with a published integrity baseline."""


def create_object(file, kind, key, *, bucket=None):
    """Allocate one location; existing artifacts always use their own references."""
    is_new = file._state.adding  # noqa: SLF001 pylint: disable=protected-access
    return ObjectStorageObject.objects.create(
        file=None if is_new else file,
        file_identifier=file.pk,
        kind=kind,
        storage_bucket_name=bucket or file.original_object.storage_bucket_name,
        key=key,
    )


def allocate_file_objects(file):
    """Allocate both upload locations before inserting a new owning file."""
    profile = get_profile_for_email(file.creator.email if file.creator_id else None)
    extension = splitext(file.filename)[1]
    for field, kind, prefix in (
        (
            "original_object",
            ObjectStorageObject.Kind.ORIGINAL,
            settings.FILE_UPLOAD_PATH,
        ),
        (
            "temporary_upload_object",
            ObjectStorageObject.Kind.TEMPORARY,
            settings.FILE_UPLOAD_TMP_PATH,
        ),
    ):
        if not getattr(file, f"{field}_id"):
            setattr(
                file,
                field,
                create_object(
                    file,
                    kind,
                    f"{prefix}/{file.pk}{extension}",
                    bucket=profile.storage_bucket_name,
                ),
            )


def head_object(obj):
    """Read provider checksums if supported; never treat permission errors as absence."""
    storage = get_storage_for_object(obj)
    if not isinstance(storage, S3Storage):
        if not storage.exists(obj.key):
            return None
        return {"ContentLength": storage.size(obj.key)}
    client = storage.connection.meta.client
    params = {"Bucket": obj.storage_bucket_name, "Key": obj.key}
    try:
        try:
            return client.head_object(**params, ChecksumMode="ENABLED")
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code")
            message = error.get("Message", "").lower()
            # Some S3-compatible providers do not implement checksum retrieval.
            # Do not downgrade authorization, KMS, or transient failures.
            unsupported = code in {"NotImplemented", "UnsupportedOperation", "501"}
            unsupported |= code in {"InvalidArgument", "InvalidRequest"} and (
                "checksum" in message
            )
            if not unsupported:
                raise
            return client.head_object(**params)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ABSENT_CODES:
            return None
        raise


def metadata_values(head):
    """Keep checksum semantics separate from the opaque ETag."""
    values = {
        "size": head["ContentLength"],
        "etag": head.get("ETag", ""),
        "metadata_checked_at": timezone.now(),
    }
    for field, algorithm in CHECKSUM_FIELDS:
        if head.get(field):
            values.update(
                checksum_algorithm=algorithm,
                checksum_value=head[field],
                checksum_type=head.get("ChecksumType", "UNKNOWN"),
                checksum_source="provider",
            )
            break
    return values


def check_integrity(obj, head):
    """Compare only metadata with matching, full-object checksum semantics."""
    if head is None or obj.published_at is None:
        return
    if obj.size is not None and obj.size != head["ContentLength"]:
        raise ObjectIntegrityError("Published storage object size changed")
    values = metadata_values(head)
    if (
        obj.checksum_type == "FULL_OBJECT"
        and values.get("checksum_type") == "FULL_OBJECT"
        and obj.checksum_algorithm == values.get("checksum_algorithm")
        and obj.checksum_value != values.get("checksum_value")
    ):
        raise ObjectIntegrityError("Published storage object checksum changed")


def observe_object(obj, *, publish=False):
    """Record a HEAD observation only if no writer changed the row meanwhile."""
    before = obj.updated_at
    head = head_object(obj)
    check_integrity(obj, head)
    now = timezone.now()
    values = {"metadata_checked_at": now, "updated_at": now}
    if head is None:
        values["state"] = ObjectStorageObject.State.MISSING
    else:
        values.update(metadata_values(head))
        if publish or obj.state == ObjectStorageObject.State.AVAILABLE:
            values["state"] = ObjectStorageObject.State.AVAILABLE
            values["published_at"] = obj.published_at or now
        else:
            values["state"] = ObjectStorageObject.State.PENDING
    # A fresh checksum-less observation must not clear an existing checksum.
    # Keep the original integrity baseline, including its algorithm and provenance.
    if obj.checksum_value:
        for field in (
            "checksum_algorithm",
            "checksum_value",
            "checksum_type",
            "checksum_source",
        ):
            values.pop(field, None)
    updated = (
        ObjectStorageObject.objects.filter(
            pk=obj.pk,
            updated_at=before,
        )
        .exclude(
            state__in=[
                ObjectStorageObject.State.DELETING,
                ObjectStorageObject.State.DELETED,
            ]
        )
        .update(**values)
    )
    obj.refresh_from_db()
    return bool(updated)


def publish_object(obj, *, content=None, head=None):
    """Publish a completed write; metadata observation is not a content recheck."""
    now = timezone.now()
    values = {
        "state": ObjectStorageObject.State.AVAILABLE,
        "published_at": obj.published_at or now,
        "updated_at": now,
        "deleted_at": None,
    }
    if head is not None:
        values.update(metadata_values(head))
    if content is not None:
        values.update(
            size=len(content),
            checksum_algorithm="SHA256",
            checksum_value=base64.b64encode(hashlib.sha256(content).digest()).decode(
                "ascii"
            ),
            checksum_type="FULL_OBJECT",
            checksum_source="application",
        )
    ObjectStorageObject.objects.filter(pk=obj.pk).exclude(
        state__in=[
            ObjectStorageObject.State.DELETING,
            ObjectStorageObject.State.DELETED,
        ]
    ).update(**values)
    obj.refresh_from_db()


@transaction.atomic
def store_result(obj, storage, content, content_type):
    """Serialize bounded AI result writes and reject changes to published bytes."""
    obj = ObjectStorageObject.objects.select_for_update().get(pk=obj.pk)
    digest = base64.b64encode(hashlib.sha256(content).digest()).decode("ascii")
    if obj.state in {obj.State.DELETING, obj.State.DELETED}:
        raise ValueError("Cannot write a deleted storage object")
    if obj.published_at is not None:
        if (
            obj.checksum_algorithm != "SHA256"
            or obj.checksum_type != "FULL_OBJECT"
            or obj.checksum_value != digest
        ):
            raise ValueError("Cannot overwrite a published storage object")
        if obj.state == obj.State.AVAILABLE:
            return
    storage.connection.meta.client.put_object(
        Bucket=obj.storage_bucket_name,
        Key=obj.key,
        Body=content,
        ContentType=content_type,
    )
    publish_object(obj, content=content)


def delete_object(obj):
    """Retain a tombstone on failure so object cleanup can be retried."""
    ObjectStorageObject.objects.filter(pk=obj.pk).update(
        state=ObjectStorageObject.State.DELETING, updated_at=timezone.now()
    )
    with transaction.atomic():
        obj = ObjectStorageObject.objects.select_for_update().get(pk=obj.pk)
        get_storage_for_object(obj).delete(obj.key)
        ObjectStorageObject.objects.filter(pk=obj.pk).update(
            state=ObjectStorageObject.State.DELETED,
            deleted_at=timezone.now(),
            updated_at=timezone.now(),
        )


@transaction.atomic
def delete_file_objects(file, *, original_only=False):
    """Commit cleanup intent for tracked locations before deleting their contents."""
    objects = file.storage_objects.exclude(state=ObjectStorageObject.State.DELETED)
    if original_only:
        objects = objects.filter(
            kind__in=[
                ObjectStorageObject.Kind.ORIGINAL,
                ObjectStorageObject.Kind.TEMPORARY,
                ObjectStorageObject.Kind.AUDIO,
            ]
        )
    objects = list(objects)
    ObjectStorageObject.objects.filter(pk__in=[obj.pk for obj in objects]).update(
        state=ObjectStorageObject.State.DELETING, updated_at=timezone.now()
    )

    def delete_objects():
        for obj in objects:
            delete_object(obj)

    transaction.on_commit(delete_objects)
