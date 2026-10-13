"""Settings validation tests."""

import pytest
from pydantic import ValidationError

from audio_extractor.settings import Settings

VALID_TOKEN = "worker-token-for-tests-0123456789"


def test_settings_accept_http_url_and_normalize_trailing_slash(tmp_path):
    settings = Settings(
        api_url="https://api.example.test/api/internal/v1.0/",
        token=VALID_TOKEN,
        work_dir=tmp_path,
    )

    assert settings.api_url == "https://api.example.test/api/internal/v1.0"


@pytest.mark.parametrize("api_url", ["", "api.example.test", "ftp://example.test"])
def test_settings_reject_invalid_api_url(api_url):
    with pytest.raises(ValidationError):
        Settings(api_url=api_url, token=VALID_TOKEN)


def test_settings_reject_empty_token():
    with pytest.raises(ValidationError):
        Settings(api_url="https://api.example.test/api/internal/v1.0", token="")


def test_settings_reject_short_token():
    with pytest.raises(ValidationError):
        Settings(
            api_url="https://api.example.test/api/internal/v1.0", token="too-short"
        )


def test_settings_accept_custom_output_parameters():
    settings = Settings(
        api_url="https://api.example.test/api/internal/v1.0",
        token=VALID_TOKEN,
        output_sample_rate=24000,
        output_bitrate="96k",
    )

    assert settings.output_sample_rate == 24000
    assert settings.output_bitrate == "96k"


def test_user_agent_uses_configured_release_and_environment(config):
    settings = config.model_copy(
        update={"release": "dictaphone@abc123", "environment": "staging"}
    )

    assert settings.user_agent == (
        "dictaphone-audio-extractor/dictaphone@abc123 "
        "(mode=transcoding, environment=staging)"
    )


def test_user_agent_omits_unconfigured_release(config):
    assert config.user_agent == "dictaphone-audio-extractor (mode=transcoding)"


@pytest.mark.parametrize("mode", ["ffmpeg", "opus", "other"])
def test_settings_reject_legacy_or_unknown_modes(mode):
    with pytest.raises(ValidationError):
        Settings(
            api_url="https://api.example.test/api/internal/v1.0",
            token=VALID_TOKEN,
            mode=mode,
        )


@pytest.mark.parametrize(
    "field",
    [
        "max_runtime_seconds",
        "process_timeout_seconds",
        "job_timeout_seconds",
        "poll_interval_seconds",
        "shutdown_grace_seconds",
        "health_port",
    ],
)
def test_lifecycle_settings_reject_zero(field):
    with pytest.raises(ValidationError):
        Settings(
            api_url="https://api.example.test/api/internal/v1.0",
            token=VALID_TOKEN,
            **{field: 0},
        )


def test_worker_runtime_must_precede_watchdog():
    with pytest.raises(ValidationError):
        Settings(
            api_url="https://api.example.test/api/internal/v1.0",
            token=VALID_TOKEN,
            max_runtime_seconds=1200,
        )
