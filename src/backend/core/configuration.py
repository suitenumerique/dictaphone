"""Domain-specific Dictaphone configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

BUCKET_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])?$")


def normalize_email_domain(domain: str) -> str:
    """Normalize and validate an email domain."""
    normalized_domain = domain.strip().rstrip(".")
    try:
        return validate_email(
            f"placeholder@{normalized_domain}",
            check_deliverability=False,
            test_environment=True,
        ).domain
    except EmailNotValidError as exc:
        raise ValueError(f"Invalid email domain: {domain!r}") from exc


def get_email_domain(email: str | None) -> str | None:
    """Return the normalized domain from an email address, if available."""
    if not email:
        return None
    try:
        return validate_email(
            email, check_deliverability=False, test_environment=True
        ).domain
    except EmailNotValidError:
        return None


class DomainProfile(BaseModel):
    """Raw, partially specified configuration for one set of domains."""

    model_config = ConfigDict(extra="forbid")

    domains: list[str] = Field(default_factory=list)
    bucket: str | None = None
    trashbin_cutoff_days: int | None = Field(default=None, ge=0)
    purge_grace_days: int | None = Field(default=None, ge=0)
    original_file_data_delete_after_days: int | None = Field(default=None, ge=0)
    original_file_data_delete_after_grace_period_days: int | None = Field(
        default=None, ge=0
    )
    file_auto_hard_delete_after_days: int | None = Field(default=None, ge=0)
    file_auto_hard_delete_after_grace_period_days: int | None = Field(
        default=None, ge=0
    )

    @field_validator("domains")
    @classmethod
    def normalize_domains(cls, domains: list[str]) -> list[str]:
        """Normalize domains and reject duplicates within a profile."""
        normalized = [normalize_email_domain(domain) for domain in domains]
        if len(normalized) != len(set(normalized)):
            raise ValueError("A profile cannot contain duplicate email domains")
        return normalized

    @field_validator("bucket")
    @classmethod
    def validate_bucket(cls, bucket: str | None) -> str | None:
        """Validate an S3 bucket name when one is provided."""
        if bucket is not None and not BUCKET_PATTERN.fullmatch(bucket):
            raise ValueError(f"Invalid S3 bucket name: {bucket!r}")
        return bucket


class DomainProfiles(RootModel[dict[str, DomainProfile]]):
    """Validated collection of domain profiles."""

    model_config = ConfigDict(frozen=True)

    @property
    def profiles(self) -> dict[str, DomainProfile]:
        """Return the named profiles."""
        return self.root

    @model_validator(mode="after")
    def validate_profiles(self) -> "DomainProfiles":
        """Validate relationships between profiles and their domains."""
        if not self.root:
            return self
        if "default" not in self.root:
            raise ValueError("A default domain profile is required")
        if self.root["default"].domains:
            raise ValueError("The default profile cannot declare email domains")

        domains_to_profiles = {}
        for profile_name, profile in self.root.items():
            for domain in profile.domains:
                previous_profile = domains_to_profiles.setdefault(domain, profile_name)
                if previous_profile != profile_name:
                    raise ValueError(
                        f"Email domain {domain!r} is configured in multiple profiles"
                    )
        return self


class ResolvedDomainProfile(BaseModel):
    """Complete immutable configuration used by the application."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    domains: tuple[str, ...]
    bucket: str
    trashbin_cutoff_days: int = Field(ge=0)
    purge_grace_days: int = Field(ge=0)
    original_file_data_delete_after_days: int = Field(ge=0)
    original_file_data_delete_after_grace_period_days: int = Field(ge=0)
    file_auto_hard_delete_after_days: int = Field(ge=0)
    file_auto_hard_delete_after_grace_period_days: int = Field(ge=0)


@dataclass(frozen=True)
class ConfigurationDefaults:
    """Global settings used to complete partially specified profiles."""

    bucket: str
    trashbin_cutoff_days: int
    purge_grace_days: int
    original_file_data_delete_after_days: int
    original_file_data_delete_after_grace_period_days: int
    file_auto_hard_delete_after_days: int
    file_auto_hard_delete_after_grace_period_days: int

    @classmethod
    def from_settings(cls, settings_obj) -> "ConfigurationDefaults":
        """Build defaults from a Django settings object or configuration class."""
        return cls(
            bucket=settings_obj.AWS_STORAGE_BUCKET_NAME,
            trashbin_cutoff_days=settings_obj.TRASHBIN_CUTOFF_DAYS,
            purge_grace_days=settings_obj.PURGE_GRACE_DAYS,
            original_file_data_delete_after_days=(
                settings_obj.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS
            ),
            original_file_data_delete_after_grace_period_days=(
                settings_obj.ORIGINAL_FILE_DATA_DELETE_AFTER_GRACE_PERIOD_DAYS
            ),
            file_auto_hard_delete_after_days=settings_obj.FILE_AUTO_HARD_DELETE_AFTER_DAYS,
            file_auto_hard_delete_after_grace_period_days=(
                settings_obj.FILE_AUTO_HARD_DELETE_AFTER_GRACE_PERIOD_DAYS
            ),
        )


def _resolve_profile(
    name: str, profile: DomainProfile, defaults: ConfigurationDefaults
) -> ResolvedDomainProfile:
    """Complete one raw profile from global defaults."""
    values = profile.model_dump(exclude={"domains", "bucket"})
    return ResolvedDomainProfile(
        name=name,
        domains=tuple(profile.domains),
        bucket=profile.bucket or defaults.bucket,
        **{
            key: value
            if value is not None
            else getattr(defaults, key)
            for key, value in values.items()
        },
    )


def resolve_profiles(raw_profiles: Any, settings_obj) -> tuple[ResolvedDomainProfile, ...]:
    """Validate and resolve all configured profiles."""
    parsed = DomainProfiles.model_validate(raw_profiles or {})
    defaults = ConfigurationDefaults.from_settings(settings_obj)
    if not parsed.profiles:
        return (_resolve_profile("default", DomainProfile(), defaults),)
    return tuple(
        _resolve_profile(name, profile, defaults)
        for name, profile in parsed.profiles.items()
    )


def get_profiles() -> tuple[ResolvedDomainProfile, ...]:
    """Return the configured, fully resolved profiles."""
    return resolve_profiles(settings.EMAIL_DOMAIN_CONFIGURATIONS, settings)


def get_profile_for_email(email: str | None) -> ResolvedDomainProfile:
    """Resolve the profile matching an email address."""
    profiles = get_profiles()
    default_profile = next(profile for profile in profiles if profile.name == "default")
    if not email:
        return default_profile

    domain = get_email_domain(email)
    if domain is None:
        return default_profile

    return next(
        (profile for profile in profiles if domain in profile.domains),
        default_profile,
    )
