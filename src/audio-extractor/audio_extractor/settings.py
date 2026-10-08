"""Validated settings for the audio extraction worker."""

from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker settings loaded from AUDIO_EXTRACTOR_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="AUDIO_EXTRACTOR_",
        frozen=True,
        extra="ignore",
    )

    api_url: str
    token: SecretStr = Field(min_length=32)
    mode: Literal["transcoding", "validation"] = "transcoding"
    output_sample_rate: int = Field(default=16000, gt=0)
    output_bitrate: str = Field(default="64k", pattern=r"^[1-9][0-9]*[kKmM]$")
    request_timeout: float = Field(default=30, gt=0)
    command_timeout: float = Field(default=900, gt=0)
    work_dir: Path = Field(default=Path("/work"))
    max_input_bytes: int = Field(default=1024 * 1024 * 1024, gt=0)

    @field_validator("api_url")
    @classmethod
    def validate_and_normalize_api_url(cls, value: str) -> str:
        """Validate the HTTP URL and remove trailing slashes."""
        validated_url = TypeAdapter(AnyHttpUrl).validate_python(value)
        return str(validated_url).rstrip("/")
