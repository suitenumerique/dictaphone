"""Gateway startup and shared Sentry credential scrubbing regression tests."""

import json
from unittest.mock import Mock
from urllib.parse import quote

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from audio_extractor import sentry
from audio_extractor.s3_gateway import app as gateway_app
from audio_extractor.s3_gateway.settings import GatewaySettings
from audio_extractor.settings import get_release

SIGNED_URL = (
    "https://user:password@storage.example.com/bucket/files/audio.ogg"
    "?X-Amz-Credential=credential&X-Amz-Signature=signature#fragment"
)
SAFE_URL = "https://storage.example.com/bucket/files/audio.ogg?[redacted]"


def test_gateway_initializes_sentry_before_creating_app(monkeypatch):
    monkeypatch.setenv("S3_GATEWAY_RULES", "[]")
    monkeypatch.setenv("SENTRY_DSN", "https://public@sentry.example.com/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")
    monkeypatch.setenv("S3_GATEWAY_ENVIRONMENT", "staging")
    monkeypatch.delenv("AUDIO_EXTRACTOR_API_URL", raising=False)
    monkeypatch.delenv("AUDIO_EXTRACTOR_TOKEN", raising=False)
    calls = Mock()
    monkeypatch.setattr(gateway_app, "init_sentry", calls.init_sentry)
    monkeypatch.setattr(gateway_app, "create_app", calls.create_app)
    monkeypatch.setattr(gateway_app.web, "run_app", calls.run_app)

    gateway_app.main()

    config = calls.init_sentry.call_args.args[0]
    assert config.sentry_dsn.get_secret_value() == "https://public@sentry.example.com/1"
    assert config.sentry_traces_sample_rate == 0.25
    assert config.environment == "staging"
    assert config.release == get_release()
    assert [call[0] for call in calls.mock_calls] == [
        "init_sentry",
        "create_app",
        "run_app",
    ]
    calls.init_sentry.assert_called_once_with(config, application="s3-gateway")


@pytest.mark.parametrize("encoding", [str, quote, lambda url: url.replace("/", "\\/")])
def test_gateway_sentry_scrubs_events_transactions_and_breadcrumbs(
    monkeypatch, encoding
):
    envelopes = []

    class MemoryTransport(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)

    def initialize(**options):
        client = sentry_sdk.Client(
            **options, transport=MemoryTransport(), default_integrations=False
        )
        sentry_sdk.get_isolation_scope().set_client(client)

    monkeypatch.setattr(sentry_sdk, "init", initialize)
    config = GatewaySettings(
        rules="[]", SENTRY_DSN="https://public@sentry.example.com/1"
    )
    with sentry_sdk.isolation_scope():
        sentry.init_sentry(config, application="s3-gateway")
        client = sentry_sdk.get_client()
        try:
            assert client.options["include_local_variables"] is False
            assert client.options["max_request_body_size"] == "never"
            assert client.options["enable_logs"] is False
            assert client.options["send_default_pii"] is False
            sentry_sdk.add_breadcrumb(message=encoding(SIGNED_URL))
            sentry_sdk.capture_event(
                {
                    "message": f"Transfer failed: {encoding(SIGNED_URL)}",
                    "request": {"headers": {"X-Target-URL": SIGNED_URL}},
                    "extra": {"nested": [encoding(SIGNED_URL)]},
                }
            )
            event = envelopes[0].items[0].payload.json
            assert event["tags"]["application"] == "s3-gateway"
            assert event["request"]["headers"]["X-Target-URL"] == SAFE_URL
            assert event["extra"]["nested"] == [SAFE_URL]
            assert event["breadcrumbs"]["values"][0]["message"] == SAFE_URL
            assert event["message"] == f"Transfer failed: {SAFE_URL}"
            assert "signature" not in json.dumps(event)
            transaction = client.options["before_send_transaction"](
                {"spans": [{"description": encoding(SIGNED_URL)}]}, {}
            )
            assert transaction == {"spans": [{"description": SAFE_URL}]}
        finally:
            client.close()
