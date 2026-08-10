"""Tests for domain-specific configuration resolution."""

import pytest
from pydantic import ValidationError

from core.configuration import (
    DomainProfiles,
    get_email_domain,
    get_profile_for_email,
    normalize_email_domain,
)


def _profiles():
    return {
        "default": {"bucket": "default-bucket"},
        "alpha": {
            "domains": ["Example.COM."],
            "bucket": "alpha-bucket",
            "file_auto_hard_delete_after_days": 10,
        },
    }


def test_email_domains_are_normalized_and_validated_by_email_validator():
    """Email addresses and configured domains use the same normalization rules."""
    assert normalize_email_domain(" Exämple.COM. ") == "exämple.com"
    assert get_email_domain("user@Exämple.COM") == "exämple.com"
    assert get_email_domain("not-an-email") is None


def test_profiles_are_normalized_and_resolved(settings):
    """Profiles should normalize domains and inherit global values."""
    settings.EMAIL_DOMAIN_CONFIGURATIONS = _profiles()

    profile = get_profile_for_email("user@example.com")

    assert profile.name == "alpha"
    assert profile.domains == ("example.com",)
    assert profile.bucket == "alpha-bucket"
    assert profile.file_auto_hard_delete_after_days == 10
    assert profile.original_file_data_delete_after_days == (
        settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS
    )


@pytest.mark.parametrize("email", [None, "user@unknown.example", "not-an-email"])
def test_profile_resolution_uses_default(settings, email):
    """Unknown or missing emails should use the default profile."""
    settings.EMAIL_DOMAIN_CONFIGURATIONS = _profiles()

    assert get_profile_for_email(email).name == "default"


def test_duplicate_domains_are_rejected():
    """A domain cannot belong to more than one profile."""
    with pytest.raises(ValidationError, match="multiple profiles"):
        DomainProfiles.model_validate(
            {
                "default": {},
                "alpha": {"domains": ["example.com"]},
                "beta": {"domains": ["EXAMPLE.COM"]},
            }
        )


def test_missing_default_profile_is_rejected():
    """Configured profiles must include a default profile."""
    with pytest.raises(ValidationError, match="default domain profile"):
        DomainProfiles.model_validate({"alpha": {"domains": ["example.com"]}})


def test_default_profile_cannot_match_a_domain():
    """The default profile is the fallback and cannot declare domains."""
    with pytest.raises(ValidationError, match="default profile"):
        DomainProfiles.model_validate(
            {"default": {"domains": ["example.com"]}}
        )
