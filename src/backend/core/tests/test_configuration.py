"""Tests for domain-specific configuration resolution."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from core.configuration import (
    BucketConfigurations,
    DataPolicyConfigurations,
    get_email_domain,
    get_profile_for_email,
    get_profiles,
    normalize_email_domain,
    resolve_profiles,
    resolve_runtime_configuration,
)


def _profiles():
    return {
        "default": {"default": True, "bucket": "default"},
        "alpha": {
            "domains": ["Example.COM."],
            "bucket": "alpha",
            "file_auto_hard_delete_after_days": 10,
        },
    }


def test_email_domains_are_normalized_and_validated_by_email_validator():
    """Email addresses and configured domains use the same normalization rules."""
    assert normalize_email_domain(" Exämple.COM. ") == "exämple.com"
    assert get_email_domain("user@Exämple.COM") == "exämple.com"
    assert get_email_domain("not-an-email") is None


def _buckets():
    return {
        "default": {
            "bucket_name": "default-bucket",
            "access_key_id_env": "S3_DEFAULT_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_DEFAULT_SECRET_ACCESS_KEY",
        },
        "alpha": {
            "bucket_name": "alpha-bucket",
            "access_key_id_env": "S3_ALPHA_ACCESS_KEY_ID",
            "secret_access_key_env": "S3_ALPHA_SECRET_ACCESS_KEY",
        },
    }


def test_profiles_are_normalized_and_resolved(settings):
    """Profiles should normalize domains and inherit global values."""
    settings.DATA_POLICY_CONFIGURATIONS = _profiles()
    settings.S3_BUCKET_CONFIGURATIONS = _buckets()

    profile = get_profile_for_email("user@example.com")

    assert profile.name == "alpha"
    assert profile.domains == ("example.com",)
    assert profile.bucket == "alpha"
    assert profile.storage_bucket_name == "alpha-bucket"
    assert profile.file_auto_hard_delete_after_days == 10
    assert profile.original_file_data_delete_after_days == (
        settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS
    )


def test_runtime_configuration_is_resolved_once(settings):
    """Repeated lookups reuse the resolved configuration registry."""
    settings.DATA_POLICY_CONFIGURATIONS = _profiles()
    settings.S3_BUCKET_CONFIGURATIONS = _buckets()

    with patch(
        "core.configuration.resolve_runtime_configuration",
        wraps=resolve_runtime_configuration,
    ) as resolve_runtime:
        get_profiles()
        get_profile_for_email("user@example.com")

    assert resolve_runtime.call_count == 1


@pytest.mark.parametrize("email", [None, "user@unknown.example", "not-an-email"])
def test_profile_resolution_uses_default(settings, email):
    """Unknown or missing emails should use the default profile."""
    settings.DATA_POLICY_CONFIGURATIONS = _profiles()
    settings.S3_BUCKET_CONFIGURATIONS = _buckets()

    assert get_profile_for_email(email).name == "default"


def test_duplicate_domains_are_rejected():
    """A domain cannot belong to more than one profile."""
    with pytest.raises(ValidationError, match="multiple data policies"):
        DataPolicyConfigurations.model_validate(
            {
                "default": {"default": True},
                "alpha": {"domains": ["example.com"]},
                "beta": {"domains": ["EXAMPLE.COM"]},
            }
        )


def test_missing_default_profile_is_rejected():
    """Configured profiles must include a default profile."""
    with pytest.raises(ValidationError, match="Exactly one data policy"):
        DataPolicyConfigurations.model_validate({"alpha": {"domains": ["example.com"]}})


def test_default_profile_cannot_match_a_domain():
    """The default profile is the fallback and cannot declare domains."""
    with pytest.raises(ValidationError, match="default data policy"):
        DataPolicyConfigurations.model_validate(
            {"default": {"default": True, "domains": ["example.com"]}}
        )


def test_policy_bucket_reference_must_be_configured(settings):
    """Every policy bucket reference must point to a configured bucket."""
    with pytest.raises(ValueError, match="unknown bucket"):
        resolve_profiles(
            {"default": {"default": True, "bucket": "missing"}},
            settings,
            {},
        )


def test_bucket_configuration_requires_default():
    """Bucket configurations must include the default bucket."""
    with pytest.raises(ValidationError, match="default bucket"):
        BucketConfigurations.model_validate(
            {
                "alpha": {
                    "bucket_name": "alpha-bucket",
                    "access_key_id_env": "S3_ALPHA_ACCESS_KEY_ID",
                    "secret_access_key_env": "S3_ALPHA_SECRET_ACCESS_KEY",
                }
            }
        )


def test_bucket_configuration_requires_unique_physical_bucket_names():
    """Logical bucket configurations cannot share a physical bucket name."""
    with pytest.raises(ValidationError, match="bucket names must be unique"):
        BucketConfigurations.model_validate(
            {
                "default": {
                    "bucket_name": "shared-bucket",
                    "access_key_id_env": "S3_DEFAULT_ACCESS_KEY_ID",
                    "secret_access_key_env": "S3_DEFAULT_SECRET_ACCESS_KEY",
                },
                "alpha": {
                    "bucket_name": "shared-bucket",
                    "access_key_id_env": "S3_ALPHA_ACCESS_KEY_ID",
                    "secret_access_key_env": "S3_ALPHA_SECRET_ACCESS_KEY",
                },
            }
        )
