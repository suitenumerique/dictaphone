"""HTTP session setup tests."""

from audio_extractor.http_client import configure_session


def test_configured_session_sets_release_mode_and_environment(http_session, config):
    configured = config.model_copy(
        update={
            "release": "dictaphone@abc123",
            "environment": "staging",
            "mode": "validation",
        }
    )

    session = configure_session(configured)

    assert session.headers["User-Agent"] == (
        "dictaphone-audio-extractor/dictaphone@abc123 "
        "(mode=validation, environment=staging)"
    )
