"""Pydantic models for the audio job API."""

from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

_HTTP_URL = TypeAdapter(AnyHttpUrl)


def _validate_url(value: str) -> str:
    """Validate a signed URL without rewriting its query string."""
    _HTTP_URL.validate_python(value)
    return value


class AudioJob(BaseModel):
    """Common fields returned by an audio job next endpoint."""

    id: str = Field(min_length=1)
    source_url: str

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        """Require a valid HTTP source URL without rewriting it."""
        return _validate_url(value)


class TranscodingJob(AudioJob):
    """A job that requires an output upload."""

    job_kind: Literal["transcoding"]
    destination_url: str
    destination_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("destination_url")
    @classmethod
    def validate_destination_url(cls, value: str) -> str:
        """Require a valid HTTP destination URL without rewriting it."""
        return _validate_url(value)


class ValidationJob(AudioJob):
    """A job that only requires validating its source audio."""

    job_kind: Literal["validation"]


class TranscodingCompletion(BaseModel):
    """Completion payload accepted by the transcoding endpoint."""

    id: str = Field(min_length=1)
    status: Literal["success", "failure"]
    duration_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    error: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, float | int] | None = None

    @model_validator(mode="after")
    def require_result_fields(self) -> "TranscodingCompletion":
        """Require duration on success and an error message on failure."""
        if self.status == "success" and (
            self.duration_seconds is None or self.error is not None
        ):
            raise ValueError("Successful transcoding completion requires a duration")
        if self.status == "failure" and not self.error:
            raise ValueError("Failed transcoding completion requires an error")
        if self.status == "failure" and self.duration_seconds is not None:
            raise ValueError("Failed transcoding completion cannot include a duration")
        return self


class ValidationCompletion(BaseModel):
    """Completion payload accepted by the validation endpoint."""

    id: str = Field(min_length=1)
    status: Literal["success", "failure"]
    error: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, float | int] | None = None

    @model_validator(mode="after")
    def require_error_on_failure(self) -> "ValidationCompletion":
        """Require an error message when validation fails."""
        if self.status == "failure" and not self.error:
            raise ValueError("Failed validation completion requires an error")
        if self.status == "success" and self.error is not None:
            raise ValueError("Successful validation completion cannot include an error")
        return self
