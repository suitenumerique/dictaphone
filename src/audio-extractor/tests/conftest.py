"""Shared fixtures for audio extractor tests."""

import pytest

from audio_extractor.api_models import TranscodingJob
from audio_extractor.settings import Settings


@pytest.fixture
def config(tmp_path):
    return Settings(
        api_url="https://api.example.test",
        token="worker-token-for-tests-0123456789",
        work_dir=tmp_path,
    )


@pytest.fixture
def task():
    return TranscodingJob(
        job_kind="transcoding",
        id="job-123",
        source_url="https://storage.test/signed-get?signature=unchanged",
        destination_url="https://storage.test/signed-put?signature=unchanged",
    )
