"""Validation of API job responses and completion payloads."""

import pytest
from pydantic import ValidationError

from audio_extractor.api_models import (
    TranscodingCompletion,
    TranscodingJob,
    ValidationCompletion,
    ValidationJob,
)


def test_job_models_validate_required_urls_and_preserve_signed_urls():
    source_url = "https://storage.example/source?X-Amz-Signature=abc%2Fdef"
    destination_url = "https://storage.example/destination?signature=xyz%2F123"

    transcoding_job = TranscodingJob(
        job_kind="transcoding",
        id="job-123",
        source_url=source_url,
        destination_url=destination_url,
    )
    validation_job = ValidationJob(
        job_kind="validation", id="job-123", source_url=source_url
    )

    assert transcoding_job.source_url == source_url
    assert transcoding_job.destination_url == destination_url
    assert validation_job.source_url == source_url


@pytest.mark.parametrize(
    "values",
    [
        {"id": "job-1", "source_url": "not a URL"},
        {"id": "", "source_url": "https://storage.example/source"},
    ],
)
def test_validation_job_rejects_invalid_response(values):
    with pytest.raises(ValidationError):
        ValidationJob.model_validate(values)


def test_transcoding_completion_requires_duration_on_success():
    completion = TranscodingCompletion(
        id="job-123", status="success", duration_seconds=3.5
    )

    assert completion.model_dump(exclude_none=True) == {
        "id": "job-123",
        "status": "success",
        "duration_seconds": 3.5,
    }
    with pytest.raises(ValidationError):
        TranscodingCompletion(id="job-123", status="success")


def test_validation_completion_requires_error_on_failure():
    completion = ValidationCompletion(
        id="job-123", status="failure", error="invalid audio"
    )

    assert completion.model_dump(exclude_none=True) == {
        "id": "job-123",
        "status": "failure",
        "error": "invalid audio",
    }
    with pytest.raises(ValidationError):
        ValidationCompletion(id="job-123", status="failure")
