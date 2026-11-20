"""Test HEAD-based reconciliation of pending storage records."""

from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

import pytest
from botocore.exceptions import ClientError
from storages.backends.s3 import S3Storage

from core import factories, models

pytestmark = pytest.mark.django_db
COMMAND = "reconcile_pending_storage_objects"
SOURCE_BUCKET = "previous-bucket"
HEAD = {
    "ContentLength": 42,
    "ChecksumSHA256": "checksum",
    "ChecksumType": "FULL_OBJECT",
    "ETag": "observed-etag",
}


@pytest.mark.parametrize("dry_run", [True, False])
def test_reconcile_pending_rows_in_one_bucket(dry_run):
    """Check every pending kind regardless of its owner's lifecycle and deadlines."""
    file = factories.FileFactory()
    original, temporary = file.original_object, file.temporary_upload_object
    other_bucket = factories.FileFactory().original_object
    non_pending = factories.FileFactory().original_object
    expired = timezone.now() - timedelta(days=1)
    models.File.objects.filter(pk=file.pk).update(
        lifecycle_state="original_data_deleted",
        original_file_data_delete_at=expired,
        original_file_data_delete_at_with_grace_period=expired,
        trashbin_purge_at=expired,
        trashbin_purge_at_with_grace_period=expired,
        deleted_at=expired,
        hard_deleted_at=expired,
    )
    models.ObjectStorageObject.objects.filter(
        pk__in=[original.pk, temporary.pk, non_pending.pk]
    ).update(storage_bucket_name=SOURCE_BUCKET)
    models.ObjectStorageObject.objects.filter(pk=non_pending.pk).update(
        state="available"
    )

    def check_key(**request):
        assert request["Bucket"] == SOURCE_BUCKET
        if request["Key"] == original.key:
            return HEAD
        raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

    stdout = StringIO()
    storage = Mock(spec=S3Storage)
    head = storage.connection.meta.client.head_object
    head.side_effect = check_key
    with patch("core.object_storage.get_storage_for_object", return_value=storage):
        call_command(
            COMMAND, source_bucket=SOURCE_BUCKET, dry_run=dry_run, stdout=stdout
        )
    assert {call.kwargs["Key"] for call in head.call_args_list} == {
        original.key,
        temporary.key,
    }

    assert "available=1, deleted=1, skipped=0, failed=0" in stdout.getvalue()
    original.refresh_from_db()
    temporary.refresh_from_db()
    other_bucket.refresh_from_db()
    assert other_bucket.state == "pending"
    if dry_run:
        assert stdout.getvalue().startswith("Dry run: ")
        assert original.state == temporary.state == "pending"
        assert original.published_at is temporary.deleted_at is None
    else:
        assert original.state == "available"
        assert original.published_at is not None
        assert original.metadata_checked_at is not None
        assert original.size == HEAD["ContentLength"]
        assert original.checksum_value == HEAD["ChecksumSHA256"]
        assert temporary.state == "deleted"
        assert temporary.deleted_at is not None
        assert temporary.metadata_checked_at is not None


def test_reconcile_continues_after_head_error():
    """A forbidden HEAD leaves the row pending and independent rows still reconcile."""
    file = factories.FileFactory()
    objects = file.storage_objects.order_by("pk")
    denied, present = objects
    objects.update(storage_bucket_name=SOURCE_BUCKET)
    error = ClientError({"Error": {"Code": "403"}}, "HeadObject")
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch(
            "core.management.commands.reconcile_pending_storage_objects.head_object",
            side_effect=[error, HEAD],
        ),
        pytest.raises(CommandError, match="1 checks failed"),
    ):
        call_command(
            COMMAND,
            source_bucket=SOURCE_BUCKET,
            batch_size=1,
            stdout=stdout,
            stderr=stderr,
        )
    assert "available=1, deleted=0, skipped=0, failed=1" in stdout.getvalue()
    assert stderr.getvalue() == f"object={denied.pk}: ClientError\n"
    assert dict(objects.values_list("pk", "state")) == {
        denied.pk: "pending",
        present.pk: "available",
    }


def test_reconcile_skips_object_changed_during_head():
    """A stale observation cannot overwrite another worker's update."""
    file = factories.FileFactory()
    objects = file.storage_objects.order_by("pk")
    objects.update(storage_bucket_name=SOURCE_BUCKET)

    def change_state(obj):
        objects.filter(pk=obj.pk).update(state="deleting")
        return HEAD

    stdout = StringIO()
    with patch(
        "core.management.commands.reconcile_pending_storage_objects.head_object",
        side_effect=change_state,
    ) as head:
        call_command(COMMAND, source_bucket=SOURCE_BUCKET, limit=1, stdout=stdout)
        head.assert_called_once()
    assert "available=0, deleted=0, skipped=1, failed=0" in stdout.getvalue()
    assert dict(objects.values_list("pk", "state")) == {
        objects[0].pk: "deleting",
        objects[1].pk: "pending",
    }
