"""Domain-specific Dictaphone configuration."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from os import environ
from types import MappingProxyType
from typing import Any, Literal, TypeVar

from django.conf import settings
from django.db.models import Model, Q, QuerySet
from django.utils import timezone

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SecretStr,
    field_validator,
    model_validator,
)

BUCKET_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])?$")
ENVIRONMENT_VARIABLE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SNAPSHOT_FIELDS = (
    "storage_bucket_name",
    "original_file_data_delete_at",
    "original_file_data_delete_at_with_grace_period",
    "file_auto_hard_delete_at",
    "file_auto_hard_delete_at_with_grace_period",
)
TRASHBIN_DEADLINE_FIELDS = (
    "trashbin_purge_at",
    "trashbin_purge_at_with_grace_period",
)
RetentionPolicy = Literal["trashbin", "original_file_data", "file_hard_delete"]
CutoffComparison = Literal["lte", "gt"]
RetentionBaseField = Literal["created_at", "deleted_at"]
ModelT = TypeVar("ModelT", bound=Model)
_configuration_cache_clearers: list[Callable[[], None]] = []
RETENTION_DEADLINE_FIELDS: dict[RetentionPolicy, tuple[str, str]] = {
    "trashbin": ("trashbin_purge_at", "trashbin_purge_at_with_grace_period"),
    "original_file_data": (
        "original_file_data_delete_at",
        "original_file_data_delete_at_with_grace_period",
    ),
    "file_hard_delete": (
        "file_auto_hard_delete_at",
        "file_auto_hard_delete_at_with_grace_period",
    ),
}


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


@lru_cache(maxsize=2048)
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


class BucketConfiguration(BaseModel):
    """Raw configuration for one named S3 bucket."""

    model_config = ConfigDict(extra="forbid")

    bucket_name_env: str
    access_key_id_env: str
    secret_access_key_env: str
    endpoint_url_env: str | None = None
    region_name: str | None = None
    signature_version: str = "s3v4"
    domain_replace: str | None = None

    @field_validator(
        "bucket_name_env",
        "access_key_id_env",
        "secret_access_key_env",
        "endpoint_url_env",
    )
    @classmethod
    def validate_environment_variable_name(cls, name: str | None) -> str | None:
        """Validate an environment variable name."""
        if name is None:
            return None
        if not ENVIRONMENT_VARIABLE_PATTERN.fullmatch(name):
            raise ValueError(f"Invalid environment variable name: {name!r}")
        return name


class BucketConfigurations(RootModel[dict[str, BucketConfiguration]]):
    """Validated collection of named S3 bucket configurations."""

    model_config = ConfigDict(frozen=True)

    @property
    def buckets(self) -> dict[str, BucketConfiguration]:
        """Return the named bucket configurations."""
        return self.root

    @model_validator(mode="after")
    def validate_default_bucket(self) -> "BucketConfigurations":
        """Require an explicit default bucket configuration."""
        if "default" not in self.root:
            raise ValueError("A default bucket configuration is required")
        return self


class DataPolicyConfiguration(BaseModel):
    """Raw, partially specified configuration for one data policy."""

    model_config = ConfigDict(extra="forbid")

    default: bool = False
    domains: tuple[str, ...] = Field(default_factory=tuple)
    bucket: str = "default"
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
    def normalize_domains(cls, domains: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize domains and reject duplicates within a profile."""
        normalized = tuple(normalize_email_domain(domain) for domain in domains)
        if len(normalized) != len(set(normalized)):
            raise ValueError("A profile cannot contain duplicate email domains")
        return normalized


class DataPolicyConfigurations(RootModel[dict[str, DataPolicyConfiguration]]):
    """Validated collection of data policies."""

    model_config = ConfigDict(frozen=True)

    @property
    def policies(self) -> dict[str, DataPolicyConfiguration]:
        """Return the named policies."""
        return self.root

    @model_validator(mode="after")
    def validate_policies(self) -> "DataPolicyConfigurations":
        """Validate default selection and relationships between domains."""
        default_policies = [
            name for name, policy in self.root.items() if policy.default
        ]
        if len(default_policies) != 1:
            raise ValueError("Exactly one data policy must be marked as default")

        domains_to_profiles = {}
        for profile_name, profile in self.root.items():
            if profile.default and profile.domains:
                raise ValueError("The default data policy cannot declare domains")
            if not profile.default and not profile.domains:
                raise ValueError(
                    f"Data policy {profile_name!r} must declare email domains"
                )
            for domain in profile.domains:
                previous_profile = domains_to_profiles.setdefault(domain, profile_name)
                if previous_profile != profile_name:
                    raise ValueError(
                        f"Email domain {domain!r} is configured in multiple data policies"
                    )
        return self


class ResolvedBucketConfiguration(BaseModel):
    """Complete immutable configuration for one S3 bucket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bucket_configuration_key: str
    storage_bucket_name: str
    access_key_id: SecretStr
    secret_access_key: SecretStr
    endpoint_url: str | None
    region_name: str | None
    signature_version: str
    domain_replace: str | None


class ResolvedDomainProfile(BaseModel):
    """Complete immutable configuration used by the application."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    default: bool
    domains: tuple[str, ...]
    bucket: str
    storage_bucket_name: str
    trashbin_cutoff_days: int = Field(ge=0)
    purge_grace_days: int = Field(ge=0)
    original_file_data_delete_after_days: int = Field(ge=0)
    original_file_data_delete_after_grace_period_days: int = Field(ge=0)
    file_auto_hard_delete_after_days: int = Field(ge=0)
    file_auto_hard_delete_after_grace_period_days: int = Field(ge=0)

    def as_file_snapshot(self, reference_time: datetime) -> dict[str, Any]:
        """Return values suitable for persisting on a file."""
        return {
            "storage_bucket_name": self.storage_bucket_name,
            "original_file_data_delete_at": reference_time
            + timedelta(days=self.original_file_data_delete_after_days),
            "original_file_data_delete_at_with_grace_period": reference_time
            + timedelta(
                days=(
                    self.original_file_data_delete_after_days
                    + self.original_file_data_delete_after_grace_period_days
                )
            ),
            "file_auto_hard_delete_at": reference_time
            + timedelta(days=self.file_auto_hard_delete_after_days),
            "file_auto_hard_delete_at_with_grace_period": reference_time
            + timedelta(
                days=(
                    self.file_auto_hard_delete_after_days
                    + self.file_auto_hard_delete_after_grace_period_days
                )
            ),
        }

    def as_trashbin_snapshot(self, deleted_at: datetime) -> dict[str, datetime]:
        """Return trash-bin deadlines calculated when a file is deleted."""
        return {
            "trashbin_purge_at": deleted_at + timedelta(days=self.trashbin_cutoff_days),
            "trashbin_purge_at_with_grace_period": deleted_at
            + timedelta(days=self.trashbin_cutoff_days + self.purge_grace_days),
        }


class ResolvedFileConfiguration(BaseModel):
    """Computed configuration persisted or derived for one file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    default: bool
    bucket_configuration_key: str
    storage_bucket_name: str
    original_file_data_delete_at: datetime
    original_file_data_delete_at_with_grace_period: datetime
    file_auto_hard_delete_at: datetime
    file_auto_hard_delete_at_with_grace_period: datetime
    trashbin_purge_at: datetime | None
    trashbin_purge_at_with_grace_period: datetime | None


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Resolved configuration and indexes used by runtime lookups."""

    buckets: Mapping[str, ResolvedBucketConfiguration]
    buckets_by_physical_name: Mapping[str, str]
    profiles: tuple[ResolvedDomainProfile, ...]
    profiles_by_domain: Mapping[str, ResolvedDomainProfile]
    default_profile: ResolvedDomainProfile


@dataclass(frozen=True)
class ConfigurationDefaults:
    """Global settings used to complete partially specified profiles."""

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


def _get_environment_secret(environment_variable: str) -> SecretStr:
    """Resolve a secret from an environment variable or its mounted file."""
    file_variable = f"{environment_variable}_FILE"
    if file_variable in environ:
        with open(environ[file_variable], encoding="utf-8") as secret_file:
            return SecretStr(secret_file.read().removesuffix("\n"))
    try:
        return SecretStr(environ[environment_variable])
    except KeyError as exc:
        raise ValueError(
            f"Credential environment variable {environment_variable!r} is not set"
        ) from exc


def _get_environment_value(environment_variable: str) -> str:
    """Resolve a non-secret value from an environment variable."""
    try:
        return environ[environment_variable]
    except KeyError as exc:
        raise ValueError(
            f"Environment variable {environment_variable!r} is not set"
        ) from exc


def resolve_bucket_configurations(
    raw_buckets: Any,
) -> dict[str, ResolvedBucketConfiguration]:
    """Validate and resolve all named S3 bucket configurations."""
    parsed = BucketConfigurations.model_validate(raw_buckets or {})
    resolved_buckets = {
        name: ResolvedBucketConfiguration(
            bucket_configuration_key=name,
            storage_bucket_name=(_get_environment_value(bucket.bucket_name_env)),
            access_key_id=_get_environment_secret(bucket.access_key_id_env),
            secret_access_key=_get_environment_secret(bucket.secret_access_key_env),
            endpoint_url=(
                _get_environment_value(bucket.endpoint_url_env)
                if bucket.endpoint_url_env
                else None
            ),
            region_name=bucket.region_name,
            signature_version=bucket.signature_version,
            domain_replace=bucket.domain_replace,
        )
        for name, bucket in parsed.buckets.items()
    }
    bucket_names = [bucket.storage_bucket_name for bucket in resolved_buckets.values()]
    if len(bucket_names) != len(set(bucket_names)):
        raise ValueError("S3 bucket names must be unique")

    for bucket_name in bucket_names:
        if bucket_name is None or not BUCKET_PATTERN.fullmatch(bucket_name):
            raise ValueError(f"Invalid S3 bucket name: {bucket_name!r}")

    return resolved_buckets


def _resolve_profile(
    name: str,
    profile: DataPolicyConfiguration,
    defaults: ConfigurationDefaults,
    buckets: dict[str, ResolvedBucketConfiguration],
) -> ResolvedDomainProfile:
    """Complete one raw profile from global defaults."""
    if profile.bucket not in buckets:
        raise ValueError(
            f"Data policy {name!r} references unknown bucket {profile.bucket!r}"
        )
    values = profile.model_dump(exclude={"default", "domains", "bucket"})
    bucket = buckets[profile.bucket]
    return ResolvedDomainProfile(
        name=name,
        default=profile.default,
        domains=tuple(profile.domains),
        bucket=profile.bucket,
        storage_bucket_name=bucket.storage_bucket_name,
        **{
            key: value if value is not None else getattr(defaults, key)
            for key, value in values.items()
        },
    )


def resolve_profiles(
    raw_profiles: Any,
    settings_obj,
    buckets: dict[str, ResolvedBucketConfiguration],
) -> tuple[ResolvedDomainProfile, ...]:
    """Validate and resolve all configured profiles."""
    parsed = DataPolicyConfigurations.model_validate(raw_profiles or {})
    defaults = ConfigurationDefaults.from_settings(settings_obj)
    if not parsed.policies:
        raise ValueError("At least one data policy configuration is required")
    return tuple(
        _resolve_profile(name, profile, defaults, buckets)
        for name, profile in parsed.policies.items()
    )


def resolve_runtime_configuration(settings_obj) -> RuntimeConfiguration:
    """Resolve configuration once and build indexes for runtime lookups."""
    buckets = resolve_bucket_configurations(settings_obj.S3_BUCKET_CONFIGURATIONS)
    profiles = resolve_profiles(
        settings_obj.DATA_POLICY_CONFIGURATIONS, settings_obj, buckets
    )
    default_profile = next(profile for profile in profiles if profile.default)
    return RuntimeConfiguration(
        buckets=MappingProxyType(buckets),
        buckets_by_physical_name=MappingProxyType(
            {bucket.storage_bucket_name: name for name, bucket in buckets.items()}
        ),
        profiles=profiles,
        profiles_by_domain=MappingProxyType(
            {domain: profile for profile in profiles for domain in profile.domains}
        ),
        default_profile=default_profile,
    )


@lru_cache(maxsize=1)
def get_runtime_configuration() -> RuntimeConfiguration:
    """Return the process-level runtime configuration snapshot."""
    return resolve_runtime_configuration(settings)


def clear_configuration_cache() -> None:
    """Clear resolved configuration caches, primarily for tests."""
    get_runtime_configuration.cache_clear()
    get_email_domain.cache_clear()
    for clear_cache in _configuration_cache_clearers:
        clear_cache()


def register_configuration_cache_clearer(clear_cache: Callable[[], None]) -> None:
    """Register a cache that should be cleared with runtime configuration."""
    _configuration_cache_clearers.append(clear_cache)


def get_bucket_configurations() -> Mapping[str, ResolvedBucketConfiguration]:
    """Return the configured, fully resolved S3 buckets."""
    return get_runtime_configuration().buckets


def get_profiles() -> tuple[ResolvedDomainProfile, ...]:
    """Return the configured, fully resolved profiles."""
    return get_runtime_configuration().profiles


def get_default_profile() -> ResolvedDomainProfile:
    """Return the global configuration used by files created before this feature."""
    return get_runtime_configuration().default_profile


def get_profile_for_email(email: str | None) -> ResolvedDomainProfile:
    """Resolve the profile matching an email address."""
    runtime_configuration = get_runtime_configuration()
    domain = get_email_domain(email)
    return runtime_configuration.profiles_by_domain.get(
        domain, runtime_configuration.default_profile
    )


def get_profile_for_file(file) -> ResolvedFileConfiguration:
    """Return the persisted file policy, with default fallbacks for old rows."""
    runtime_configuration = get_runtime_configuration()
    default_profile = runtime_configuration.default_profile
    storage_bucket_name = (
        file.storage_bucket_name or default_profile.storage_bucket_name
    )
    logical_bucket_name = runtime_configuration.buckets_by_physical_name.get(
        storage_bucket_name
    )
    if logical_bucket_name is None:
        raise ValueError(
            f"File {file.pk} references unknown physical S3 bucket {storage_bucket_name!r}"
        )
    if file.storage_bucket_name:
        trashbin_snapshot = {
            field: getattr(file, field) for field in TRASHBIN_DEADLINE_FIELDS
        }
        if file.deleted_at is not None and all(
            value is None for value in trashbin_snapshot.values()
        ):
            # Rows deleted before trash-bin deadlines were introduced need a
            # deterministic fallback until they are restored or deleted again.
            trashbin_snapshot = default_profile.as_trashbin_snapshot(file.deleted_at)
        # These values are persisted on the file or derived from the already
        # validated runtime configuration, so revalidating them on every
        # property access is unnecessary.
        return ResolvedFileConfiguration.model_construct(
            name="snapshot",
            default=False,
            bucket_configuration_key=logical_bucket_name,
            storage_bucket_name=storage_bucket_name,
            **{
                field: getattr(file, field)
                for field in SNAPSHOT_FIELDS
                if field != "storage_bucket_name"
            },
            **trashbin_snapshot,
        )

    file_snapshot = default_profile.as_file_snapshot(file.created_at)
    trashbin_snapshot = (
        default_profile.as_trashbin_snapshot(file.deleted_at)
        if file.deleted_at is not None
        else dict.fromkeys(TRASHBIN_DEADLINE_FIELDS)
    )
    return ResolvedFileConfiguration.model_construct(
        name="default",
        default=True,
        bucket_configuration_key=logical_bucket_name,
        **file_snapshot,
        **trashbin_snapshot,
    )


def filter_files_by_policy_cutoff(  # noqa: PLR0913 pylint: disable=too-many-arguments
    queryset: QuerySet[ModelT],
    *,
    policy: RetentionPolicy,
    include_grace_period: bool = False,
    base_field: RetentionBaseField = "created_at",
    field_prefix: str = "",
    comparison: CutoffComparison = "lte",
) -> QuerySet[ModelT]:
    """Filter files using the retention policy persisted on each file."""
    try:
        deadline_field = RETENTION_DEADLINE_FIELDS[policy][
            1 if include_grace_period else 0
        ]
    except KeyError as exc:
        raise ValueError(f"Unknown retention policy: {policy}") from exc
    if comparison not in {"lte", "gt"}:
        raise ValueError(f"Unknown cutoff comparison: {comparison}")

    now = timezone.now()
    snapshot_query = Q(**{f"{field_prefix}{deadline_field}__{comparison}": now})
    runtime_configuration = get_runtime_configuration()
    default_profile = runtime_configuration.default_profile
    if policy == "trashbin":
        days = default_profile.trashbin_cutoff_days
        if include_grace_period:
            days += default_profile.purge_grace_days
    elif policy == "original_file_data":
        days = default_profile.original_file_data_delete_after_days
        if include_grace_period:
            days += default_profile.original_file_data_delete_after_grace_period_days
    else:
        days = default_profile.file_auto_hard_delete_after_days
        if include_grace_period:
            days += default_profile.file_auto_hard_delete_after_grace_period_days
    cutoff = now - timedelta(days=days)
    default_query = Q(**{f"{field_prefix}storage_bucket_name__isnull": True}) & Q(
        **{f"{field_prefix}{base_field}__{comparison}": cutoff}
    )

    return queryset.filter(snapshot_query | default_query)
