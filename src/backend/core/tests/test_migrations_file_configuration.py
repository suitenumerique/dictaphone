"""Regression tests for backfilling legacy file configuration snapshots."""

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

import pytest

from core.configuration import get_default_profile


@pytest.mark.django_db(transaction=True)
def test_migration_backfills_legacy_buckets_and_preserves_existing_snapshots(
    settings, monkeypatch
):
    """Populate active and deleted legacy rows before making snapshots mandatory."""
    monkeypatch.setenv("S3_DEFAULT_BUCKET_NAME", "legacy-default-bucket")
    settings.S3_BUCKET_CONFIGURATIONS = {
        "default": {
            "bucket_name_env": "S3_DEFAULT_BUCKET_NAME",
            "access_key_id_env": "S3_DEFAULT_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_DEFAULT_SECRET_ACCESS_KEY",
        }
    }
    settings.DATA_POLICY_CONFIGURATIONS = {"default": {"default": True}}
    profile = get_default_profile()
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes("core")
    before = [("core", "0015_file_audio_extraction_state")]
    after = [("core", "0016_remove_file_file_snapshot_complete_and_more")]
    file_model = None
    try:
        executor.migrate(before)
        file_model = executor.loader.project_state(before).apps.get_model(
            "core", "File"
        )
        active = file_model.objects.create(duration_seconds=1)
        deleted = file_model.objects.create(
            duration_seconds=1, deleted_at=timezone.now()
        )
        existing_values = {
            "storage_bucket_name": "existing-bucket",
            **profile.as_file_snapshot(timezone.now() - timedelta(days=10)),
        }
        existing = file_model.objects.create(duration_seconds=1, **existing_values)

        MigrationExecutor(connection).migrate(after)

        for file in (active, deleted):
            file.refresh_from_db()
            assert file.storage_bucket_name == "legacy-default-bucket"
            for field, value in profile.as_file_snapshot(file.created_at).items():
                assert getattr(file, field) == value
            if file.deleted_at is not None:
                for field, value in profile.as_trashbin_snapshot(
                    file.deleted_at
                ).items():
                    assert getattr(file, field) == value
            else:
                assert file.trashbin_purge_at is None
                assert file.trashbin_purge_at_with_grace_period is None
        existing.refresh_from_db()
        for field, value in existing_values.items():
            assert getattr(existing, field) == value
    finally:
        # Later migrations require object references; remove historical fixtures first.
        if file_model is not None:
            file_model.objects.all().delete()
        MigrationExecutor(connection).migrate(latest)
