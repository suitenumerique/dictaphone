"""Upgrade coverage for requiring a storage owner."""

from uuid import uuid4

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

import pytest

from core import factories, models


@pytest.mark.django_db(transaction=True)
def test_storage_owner_migration_requires_legacy_cleanup():
    """Preserve pending cleanup and restore owner links before requiring them."""
    previous = [("core", "0029_object_storage_deleting_index")]
    current = [("core", "0030_remove_detached_deleted_storage_objects")]
    old_apps = MigrationExecutor(connection).migrate(previous).apps
    try:
        file = factories.FileFactory()
        objects = models.ObjectStorageObject.objects
        objects.filter(pk=file.original_object_id).update(state="deleted")
        old_objects = old_apps.get_model("core", "ObjectStorageObject").objects
        detached = {
            state: old_objects.create(
                file_identifier=file.pk,
                kind="original",
                key=f"detached-{state}",
                storage_bucket_name=file.original_object.storage_bucket_name,
                state=state,
            )
            for state in ("deleted", "deleting")
        }
        orphan = old_objects.create(
            file_identifier=uuid4(),
            kind="original",
            key="orphan",
            storage_bucket_name=file.original_object.storage_bucket_name,
            state="deleting",
        )
        try:
            with pytest.raises(RuntimeError, match="Uncleaned storage objects"):
                MigrationExecutor(connection).migrate(current)
            assert old_objects.filter(pk=orphan.pk, state="deleting").exists()
        finally:
            orphan.delete()
    finally:
        MigrationExecutor(connection).migrate(current)

    assert not objects.filter(pk=detached["deleted"].pk).exists()
    restored = objects.get(pk=detached["deleting"].pk)
    assert restored.state == "deleting"
    assert restored.file_id == file.pk
    assert objects.get(pk=file.original_object_id).state == "deleted"
    with (
        pytest.raises(IntegrityError, match='null value in column "file_id"'),
        transaction.atomic(),
    ):
        objects.filter(pk=restored.pk).update(file_id=None)
