"""Repair missing storage records left by legacy backfills."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

from core import factories, models, storage_migration

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("kind", "lifecycle", "outcome", "state"),
    [
        ("original", "original_data_deleted", "migrated", "deleted"),
        ("temporary", "original_data_deleted", "migrated", "deleted"),
        ("audio", "original_data_deleted", "migrated", "deleted"),
        ("transcript", "original_data_deleted", "migrated", "missing"),
        ("original", "pending_original_data_deletion", "deferred", "missing"),
        ("original", "active", "deferred", "missing"),
        ("temporary", "active", "deferred", "missing"),
    ],
)
def test_missing_records_after_legacy_cleanup(kind, lifecycle, outcome, state):
    """Classify absence as deletion only when the file records completed cleanup."""
    file = factories.FileFactory()
    obj = file.temporary_upload_object if kind == "temporary" else file.original_object
    source_bucket = obj.storage_bucket_name
    now = timezone.now()
    models.File.objects.filter(pk=file.pk).update(
        upload_state="ready",
        lifecycle_state=lifecycle,
        original_file_data_delete_at=now - timedelta(seconds=1),
    )
    models.ObjectStorageObject.objects.filter(pk=obj.pk).update(
        state="missing",
        kind=kind,
        metadata_checked_at=now,
        # Exercise status repair in place for an already aligned audio record.
        storage_bucket_name="destination" if kind == "audio" else source_bucket,
    )
    with (
        patch.object(storage_migration, "expected_bucket", return_value="destination"),
        patch.object(
            storage_migration, "get_storage_for_object", side_effect=AssertionError
        ),
    ):
        assert storage_migration.migrate_object(obj.pk, dry_run=True) == outcome
        obj.refresh_from_db()
        assert obj.state == "missing"
        assert storage_migration.migrate_object(obj.pk) == outcome
    obj.refresh_from_db()
    assert obj.state == state
    assert obj.deleted_at is None
    assert obj.metadata_checked_at == now
    expected_bucket = source_bucket if outcome == "deferred" else "destination"
    assert obj.storage_bucket_name == expected_bucket
