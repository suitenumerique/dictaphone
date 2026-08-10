"""Storage helpers for files with domain-specific S3 buckets."""

from functools import lru_cache

from django.core.files.storage import default_storage

from storages.backends.s3 import S3Storage

from core.configuration import get_bucket_configurations


class ConfiguredS3Storage(S3Storage):  # pylint: disable=abstract-method
    """S3 storage backend configured from the logical default bucket."""

    def __init__(self, **kwargs):
        configuration = get_bucket_configurations()["default"]
        super().__init__(
            bucket_name=configuration.bucket_name,
            access_key=configuration.access_key_id.get_secret_value(),
            secret_key=configuration.secret_access_key.get_secret_value(),
            endpoint_url=configuration.endpoint_url,
            region_name=configuration.region_name,
            signature_version=configuration.signature_version,
            **kwargs,
        )


@lru_cache(maxsize=32)
def get_storage_for_bucket(bucket_configuration: str, bucket_name: str | None = None):
    """Return a storage backend configured for one bucket."""
    if not isinstance(default_storage, S3Storage):
        return default_storage

    configuration = get_bucket_configurations()[bucket_configuration]
    bucket_name = bucket_name or configuration.bucket_name

    return S3Storage(
        bucket_name=bucket_name,
        access_key=configuration.access_key_id.get_secret_value(),
        secret_key=configuration.secret_access_key.get_secret_value(),
        endpoint_url=configuration.endpoint_url,
        region_name=configuration.region_name,
        signature_version=configuration.signature_version,
    )


def get_storage_bucket_name(storage) -> str:
    """Return the configured bucket name from an S3 storage backend."""
    return storage.bucket_name


def get_storage_for_file(file):
    """Return the storage backend selected by a file's persisted configuration."""
    profile = file.configuration
    return get_storage_for_bucket(
        profile.bucket_name,
        bucket_name=file.storage_bucket_name or profile.storage_bucket_name,
    )


def get_bucket_configuration_for_file(file):
    """Return the resolved S3 configuration selected by a file."""
    return get_bucket_configurations()[file.configuration.bucket_name]
