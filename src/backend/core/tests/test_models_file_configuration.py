"""Tests for file configuration snapshots."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

import pytest

from core import factories
from core.configuration import clear_configuration_cache, get_profile_for_file

pytestmark = pytest.mark.django_db


def test_file_snapshots_creator_domain_configuration(settings, monkeypatch):
    """New files should retain the profile selected at creation time."""
    monkeypatch.setenv("S3_ALPHA_BUCKET_NAME", "alpha-bucket")
    settings.DATA_POLICY_CONFIGURATIONS = {
        "default": {"default": True},
        "alpha": {
            "domains": ["alpha.example"],
            "bucket": "alpha",
            "file_auto_hard_delete_after_days": 10,
        },
    }
    settings.S3_BUCKET_CONFIGURATIONS = {
        "default": {
            "bucket_name_env": "S3_DEFAULT_BUCKET_NAME",
            "access_key_id_env": "S3_DEFAULT_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_DEFAULT_SECRET_ACCESS_KEY",
        },
        "alpha": {
            "bucket_name_env": "S3_ALPHA_BUCKET_NAME",
            "access_key_id_env": "S3_ALPHA_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_ALPHA_SECRET_ACCESS_KEY",
        },
    }
    user = factories.UserFactory(email="user@alpha.example")

    file = factories.FileFactory(creator=user)

    assert file.storage_bucket_name == "alpha-bucket"
    assert file.file_auto_hard_delete_at == file.created_at + timedelta(days=10)

    settings.DATA_POLICY_CONFIGURATIONS = {
        "default": {"default": True, "bucket": "default"}
    }
    clear_configuration_cache()
    file.refresh_from_db()
    assert file.configuration.bucket_name == "alpha"
    assert file.configuration.file_auto_hard_delete_at == file.file_auto_hard_delete_at


def test_default_file_uses_default_configuration(settings, monkeypatch):
    """Rows without snapshots should continue using global settings."""
    file = factories.FileFactory(creator=None)
    monkeypatch.setenv("S3_DEFAULT_BUCKET_NAME", "default-bucket")
    settings.DATA_POLICY_CONFIGURATIONS = {
        "default": {"default": True, "bucket": "default"}
    }
    settings.S3_BUCKET_CONFIGURATIONS = {
        "default": {
            "bucket_name_env": "S3_DEFAULT_BUCKET_NAME",
            "access_key_id_env": "S3_DEFAULT_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_DEFAULT_SECRET_ACCESS_KEY",
        }
    }
    settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS = 12

    file.refresh_from_db()
    profile = get_profile_for_file(file)

    assert profile.name == "default"
    assert profile.bucket_name == "default"
    assert profile.storage_bucket_name == "default-bucket"
    assert profile.file_auto_hard_delete_at == file.created_at + timedelta(days=12)


def test_soft_delete_persists_current_profile_trashbin_deadlines(settings):
    """Soft deletion should persist trash-bin deadlines from the current profile."""
    settings.DATA_POLICY_CONFIGURATIONS = {
        "default": {"default": True},
        "alpha": {
            "domains": ["alpha.example"],
            "trashbin_cutoff_days": 10,
            "purge_grace_days": 2,
        },
    }
    user = factories.UserFactory(email="user@alpha.example")
    file = factories.FileFactory(creator=user)

    file.soft_delete()

    assert file.trashbin_purge_at == file.deleted_at + timedelta(days=10)
    assert file.trashbin_purge_at_with_grace_period == file.deleted_at + timedelta(
        days=12
    )

    file.restore()
    assert file.deleted_at is None
    assert file.trashbin_purge_at is None
    assert file.trashbin_purge_at_with_grace_period is None


def test_file_configuration_fields_must_be_complete():
    """Creation and trash-bin snapshots must not be partially populated."""
    file = factories.FileFactory(creator=None)
    file.storage_bucket_name = "bucket"
    with pytest.raises(ValidationError, match="file_snapshot_complete"):
        file.full_clean()
    file.storage_bucket_name = None
    file.trashbin_purge_at = timezone.now()
    with pytest.raises(ValidationError, match="file_trashbin_deadlines"):
        file.full_clean()


@pytest.mark.parametrize(
    ("deadline_field", "grace_deadline_field"),
    [
        (
            "original_file_data_delete_at",
            "original_file_data_delete_at_with_grace_period",
        ),
        ("file_auto_hard_delete_at", "file_auto_hard_delete_at_with_grace_period"),
        ("trashbin_purge_at", "trashbin_purge_at_with_grace_period"),
    ],
)
def test_file_deadlines_must_include_grace_period(
    settings, deadline_field, grace_deadline_field
):
    """Grace-period deadlines cannot precede their base deadlines."""
    settings.DATA_POLICY_CONFIGURATIONS = {"default": {"default": True}}
    file = factories.FileFactory()
    file.soft_delete()
    setattr(
        file,
        grace_deadline_field,
        getattr(file, deadline_field) - timedelta(seconds=1),
    )

    with pytest.raises(ValidationError):
        file.full_clean()
