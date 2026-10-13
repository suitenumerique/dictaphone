"""Shared fixtures for audio extractor tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from audio_extractor import supervisor
from audio_extractor.api_models import TranscodingJob
from audio_extractor.http_client import close_session, configure_session, get_session
from audio_extractor.settings import Settings


@pytest.fixture
def config(tmp_path):
    return Settings(
        api_url="https://api.example.test/api/internal/v1.0",
        token="worker-token-for-tests-0123456789",
        work_dir=tmp_path,
    )


@pytest.fixture(autouse=True)
def configured_http_session():
    settings = Settings(
        api_url="https://api.example.test/api/internal/v1.0",
        token="worker-token-for-tests-0123456789",
    )
    session = configure_session(settings)
    yield session
    close_session()


@pytest.fixture
def http_session(configured_http_session):
    return get_session()


@pytest.fixture
def task():
    return TranscodingJob(
        job_kind="transcoding",
        id="job-123",
        expires_at=datetime.now(UTC) + timedelta(seconds=300),
        source_url="https://storage.test/signed-get?signature=unchanged",
        destination_url="https://storage.test/signed-put?signature=unchanged",
    )


@pytest.fixture
def lifecycle(monkeypatch, config):
    """Run supervisor loops deterministically without sleeping or binding ports."""
    clock = [0.0]

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        def wait(self, seconds):
            clock[0] += seconds
            return self.stopped

    stop = Stop()
    monkeypatch.setattr(supervisor.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(supervisor.threading, "Event", lambda: stop)
    monkeypatch.setattr(supervisor, "HealthServer", MagicMock())
    return config.model_copy(update={"max_runtime_seconds": 1}), clock, stop
