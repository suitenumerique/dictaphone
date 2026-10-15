"""Environment settings for the isolated S3 gateway process."""

from functools import cached_property

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from audio_extractor.settings import get_release


class GatewaySettings(BaseSettings):
    """Gateway-only environment; no worker credentials or backend connections."""

    model_config = SettingsConfigDict(
        env_prefix="S3_GATEWAY_", frozen=True, allow_inf_nan=False
    )
    rules: str = Field(repr=False)
    sentry_dsn: SecretStr | None = Field(default=None, validation_alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE"
    )
    environment: str | None = None
    force_https: bool = True
    port: int = Field(default=8080, ge=1, le=65535)
    max_upload_bytes: int = Field(default=1073741824, gt=0)
    max_concurrent_requests: int = Field(default=20, gt=0)
    timeout_seconds: float = Field(default=3600, gt=0)
    connect_timeout_seconds: float = Field(default=10, gt=0)
    shutdown_grace_seconds: float = Field(default=30, gt=0)

    @cached_property
    def release(self) -> str:
        """Return the audio-extractor project version, shared with the worker."""
        return get_release()
