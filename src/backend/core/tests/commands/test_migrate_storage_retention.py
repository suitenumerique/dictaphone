"""Verify bucket migration eligibility and cutover during the trash grace period."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

from core import factories, models, storage_migration
from core.object_storage import publish_object

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("deadline", "preview", "outcome"),
    [
        ("within grace", "migrated", "migrated"),
        ("already reached", "deferred", "deferred"),
        ("reached during transfer", "migrated", "deferred"),
    ],
)
def test_trashed_object_migration_honors_grace_deadline(deadline, preview, outcome):
    """Move a trashed artifact only if its grace period lasts through cutover."""
    file = factories.FileFactory()
    obj = file.original_object
    source = obj.storage_bucket_name
    now = timezone.now()
    # All cases are past the ordinary trash deadline. Only the grace deadline varies.
    grace = timedelta(0) if deadline == "already reached" else timedelta(hours=1)
    models.File.objects.filter(pk=file.pk).update(
        upload_state="ready",
        deleted_at=now - timedelta(days=2),
        trashbin_purge_at=now - timedelta(days=1),
        trashbin_purge_at_with_grace_period=now + grace,
    )
    publish_object(obj, content=b"source bytes")

    def transfer(*_args):
        """Stand in for the S3 copy and expire the grace period before cutover."""
        if deadline == "reached during transfer":
            models.File.objects.filter(pk=file.pk).update(
                trashbin_purge_at_with_grace_period=now
            )
        return {}

    with (
        patch.object(storage_migration, "expected_bucket", return_value="destination"),
        patch.object(storage_migration, "_transfer", side_effect=transfer) as copy,
    ):
        assert storage_migration.migrate_object(obj.pk, dry_run=True) == preview
        copy.assert_not_called()
        assert storage_migration.migrate_object(obj.pk) == outcome
        assert copy.call_count == int(preview == "migrated")

    # The authoritative row points to the destination only after a successful cutover.
    obj.refresh_from_db()
    assert obj.storage_bucket_name == (
        "destination" if outcome == "migrated" else source
    )
