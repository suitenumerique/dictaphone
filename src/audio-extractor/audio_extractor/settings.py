"""Validated settings for the audio extraction worker."""

import tomllib
from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

USER_AGENT_NAME = "dictaphone-audio-extractor"


def get_release() -> str:
    """Return the audio-extractor project version for Sentry."""
    try:
        with (Path(__file__).parent.parent / "pyproject.toml").open("rb") as pyproject:
            return tomllib.load(pyproject)["project"]["version"]
    except FileNotFoundError, KeyError, tomllib.TOMLDecodeError:
        return "NA"  # Default: not available


class Settings(BaseSettings):
    """Worker settings loaded from AUDIO_EXTRACTOR_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="AUDIO_EXTRACTOR_",
        frozen=True,
        extra="ignore",
    )

    api_url: str = Field(
        description="Internal API base URL including /api/internal/${API_VERSION}"
    )
    mode: Literal["transcoding", "validation"] = "transcoding"
    transcoding_token: SecretStr | None = Field(default=None, exclude=True, repr=False)
    validation_token: SecretStr | None = Field(default=None, exclude=True, repr=False)
    token: SecretStr = Field(
        min_length=32,
        default_factory=lambda data: data[f"{data['mode']}_token"] or "",
    )
    sentry_dsn: SecretStr | None = Field(
        default=None,
        validation_alias="SENTRY_DSN",
    )
    sentry_traces_sample_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE"
    )
    environment: str | None = None
    s3_gateway_url: str | None = Field(default=None, validation_alias="S3_GATEWAY_URL")
    output_sample_rate: int = Field(default=16000, gt=0)
    output_bitrate: str = Field(default="64k", pattern=r"^[1-9][0-9]*[kKmM]$")
    request_timeout: float = Field(default=30, gt=0)
    command_timeout: float = Field(default=900, gt=0)
    work_dir: Path = Field(default=Path("/work"))
    max_input_bytes: int = Field(default=1024 * 1024 * 1024, gt=0)
    max_runtime_seconds: int = Field(default=900, gt=0)
    process_timeout_seconds: int = Field(default=1200, gt=0)
    job_timeout_seconds: int = Field(default=300, gt=0)
    poll_interval_seconds: float = Field(default=5, gt=0)
    shutdown_grace_seconds: int = Field(default=30, gt=0)
    health_port: int = Field(default=8080, ge=1, le=65535)

    @cached_property
    def release(self) -> str:
        """Return the audio-extractor project version."""
        return get_release()

    @field_validator("s3_gateway_url")
    @classmethod
    def validate_gateway_url(cls, value: str | None) -> str | None:
        """An empty variable preserves direct mode; gateway URLs are internal HTTP."""
        if not value:
            return None
        parsed = TypeAdapter(AnyHttpUrl).validate_python(value)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/proxy"
        ):
            raise ValueError("S3_GATEWAY_URL must be an HTTP(S) /proxy URL")
        return value

    @property
    def user_agent(self) -> str:
        """Identify the extractor release, environment, and processing mode."""
        identity = USER_AGENT_NAME
        if self.release != "":
            identity = f"{USER_AGENT_NAME}/{self.release}"
        environment = f", environment={self.environment}" if self.environment else ""
        return f"{identity} (mode={self.mode}{environment})"

    @model_validator(mode="after")
    def validate_lifetime(self) -> "Settings":
        """Keep the independent watchdog beyond the normal draining deadline."""
        if self.max_runtime_seconds >= self.process_timeout_seconds:
            raise ValueError(
                "MAX_RUNTIME_SECONDS must be less than PROCESS_TIMEOUT_SECONDS"
            )
        return self

    @field_validator("api_url")
    @classmethod
    def validate_and_normalize_api_url(cls, value: str) -> str:
        """Validate the HTTP URL and remove trailing slashes."""
        validated_url = TypeAdapter(AnyHttpUrl).validate_python(value)
        return str(validated_url).rstrip("/")
