"""Tests for per-file object storage selection."""

from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage

import pytest

from core import factories
from core.storage import (
    get_storage_bucket_name,
    get_storage_for_bucket,
    get_storage_for_file,
)

pytestmark = pytest.mark.django_db


def test_bucket_storage_requires_s3_backend(monkeypatch):
    """S3-specific storage helpers fail clearly with filesystem storage."""
    filesystem_storage = FileSystemStorage()
    monkeypatch.setattr("core.storage.default_storage", filesystem_storage)

    with pytest.raises(ImproperlyConfigured, match="S3Storage"):
        get_storage_for_bucket("default")

    with pytest.raises(ImproperlyConfigured, match="S3Storage"):
        get_storage_bucket_name(filesystem_storage)

    assert get_storage_for_file(None) is filesystem_storage


def test_file_storage_uses_the_creator_domain_bucket(settings, monkeypatch):
    """Files created by a configured domain use its bucket backend."""
    monkeypatch.setenv("S3_DEFAULT_BUCKET_NAME", "dictaphone-media-storage")
    monkeypatch.setenv("S3_PARTNER_BUCKET_NAME", "dictaphone-media-partner")

    settings.DATA_POLICY_CONFIGURATIONS = {
        "default": {"default": True},
        "partner": {
            "domains": ["partner.example"],
            "bucket": "partner",
        },
    }
    settings.S3_BUCKET_CONFIGURATIONS = {
        "default": {
            "bucket_name_env": "S3_DEFAULT_BUCKET_NAME",
            "access_key_id_env": "S3_DEFAULT_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_DEFAULT_SECRET_ACCESS_KEY",
        },
        "partner": {
            "bucket_name_env": "S3_PARTNER_BUCKET_NAME",
            "access_key_id_env": "S3_PARTNER_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_PARTNER_SECRET_ACCESS_KEY",
        },
    }
    monkeypatch.setenv("S3_PARTNER_ACCESS_KEY_ID", "partner-access")
    monkeypatch.setenv("S3_PARTNER_SECRET_ACCESS_KEY", "partner-secret")
    file = factories.FileFactory(
        creator=factories.UserFactory(email="person@partner.example")
    )

    storage = get_storage_for_file(file)

    assert get_storage_bucket_name(storage) == "dictaphone-media-partner"
    assert storage.access_key == "partner-access"  # pylint: disable=no-member
    assert storage.secret_key == "partner-secret"  # pylint: disable=no-member
