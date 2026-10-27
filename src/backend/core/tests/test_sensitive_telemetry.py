"""Regression tests for sensitive values in telemetry."""

import json
import logging
from unittest.mock import patch
from urllib.parse import quote

import pytest
import sentry_sdk
from rest_framework.test import APIClient
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices
from core.tasks.file import handle_transcript_received, store_summary
from core.tests.test_payloads import response_for

from dictaphone import celery_app
from dictaphone.sentry import scrub_urls


def test_sentry_scrubs_nested_and_encoded_urls():
    """Scrub credentials from nested and URL-encoded Sentry data."""
    event = {
        "message": "https://user:password@example.com/file?signature=SECRET#part",
        "breadcrumbs": ["https%3A%2F%2Fexample.com%2Ffile%3Fsignature%3DSECRET"],
    }
    result = str(scrub_urls(event))
    assert "SECRET" not in result
    assert "password" not in result
    assert "example.com/file" in result


@pytest.mark.parametrize("encoding_depth", [0, 1, 2, 3, 4])
def test_sentry_scrubs_urls_at_multiple_encoding_depths(encoding_depth):
    """Redact encoded URLs and fail closed beyond the decoding limit."""
    url = "https://example.com/file?signature=SECRET"
    for _ in range(encoding_depth):
        url = quote(url, safe="")
    result = scrub_urls(url)
    assert "SECRET" not in result
    if encoding_depth > 3:
        assert result == "[redacted URL]"
    else:
        assert result == "https://example.com/file?[redacted]"


@pytest.mark.django_db
def test_invalid_webhook_does_not_log_or_return_payload(settings, caplog):
    """Keep invalid webhook data out of logs and error responses."""
    settings.AI_WEBHOOK_API_KEY = "test-key"
    caplog.set_level(logging.DEBUG, logger="core.api.viewsets")
    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "type": "transcript",
            "status": "success",
            "job_id": "id",
            "transcription_data_url": ["SECRET"],
        },
        format="json",
        headers={"Authorization": "Bearer test-key"},
    )
    assert response.status_code == 400
    assert "SECRET" not in caplog.text
    assert b"SECRET" not in response.content


@pytest.mark.django_db
def test_valid_webhook_does_not_log_signed_url(settings, caplog):
    """Dispatch signed URLs without exposing them in debug logs."""
    settings.AI_WEBHOOK_API_KEY = "test-key"
    job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT, status=AiJobStatusChoices.PENDING
    )
    signed_url = "https://example.com/transcript?signature=SECRET"
    caplog.set_level(logging.DEBUG, logger="core.api.viewsets")
    with patch("core.api.viewsets.handle_transcript_received.apply_async") as dispatch:
        response = APIClient().post(
            "/api/v1.0/ai-jobs/webhook/",
            {
                "type": "transcript",
                "status": "success",
                "job_id": job.remote_job_id,
                "transcription_data_url": signed_url,
            },
            format="json",
            headers={"Authorization": "Bearer test-key"},
        )
    assert response.status_code == 200
    dispatch.assert_called_once_with(args=[job.remote_job_id, signed_url])
    assert "SECRET" not in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "job_type,body,task",
    [
        (
            AiJobTypeChoices.TRANSCRIPT,
            b'{"segments": [{"text": "SECRET"}], "word_segments": []}',
            handle_transcript_received,
        ),
        (AiJobTypeChoices.SUMMARIZE, b"SECRET\xff", store_summary),
    ],
)
def test_invalid_result_error_does_not_contain_data(job_type, body, task):
    """Raise sanitized errors for invalid transcripts and summaries."""
    job = factories.AiFileJobFactory(type=job_type, status=AiJobStatusChoices.PENDING)
    with patch(
        "core.tasks.file.fetch_external_source", return_value=response_for(body)
    ):
        with pytest.raises(ValueError) as exc:
            task.apply(
                args=[job.remote_job_id, "https://example.com/result"], throw=True
            )
    assert "SECRET" not in str(exc.value)
    assert exc.value.__suppress_context__


@pytest.mark.parametrize("initializer", ["init_sentry", "init_sentry_in_worker"])
def test_celery_sentry_initializers_apply_privacy_settings(monkeypatch, initializer):
    """Apply the same Sentry privacy settings to both Celery initializers."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.com/1")
    with patch.object(celery_app.sentry_sdk, "init") as init:
        getattr(celery_app, initializer)()
    options = init.call_args.kwargs
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
    assert options["before_send"] is scrub_urls
    assert options["before_send_transaction"] is scrub_urls
    assert options["before_breadcrumb"] is scrub_urls


def test_sentry_capture_scrubs_event_and_breadcrumb():
    """Scrub signed URLs from captured Sentry events and breadcrumbs."""
    envelopes = []

    class MemoryTransport(Transport):
        """Collect Sentry envelopes without sending them over the network."""

        def capture_envelope(self, envelope):
            """Store a captured envelope for inspection."""
            envelopes.append(envelope)

    with sentry_sdk.isolation_scope() as scope:
        client = sentry_sdk.Client(
            dsn="https://public@example.com/1",
            transport=MemoryTransport(),
            default_integrations=False,
            before_send=scrub_urls,
            before_breadcrumb=scrub_urls,
            include_local_variables=False,
        )
        scope.set_client(client)
        sentry_sdk.add_breadcrumb(message="https://example.com/file?token=SECRET")
        sentry_sdk.capture_event({"message": "https://example.com/file?token=SECRET"})
        event = envelopes[0].items[0].payload.json
        assert "SECRET" not in json.dumps(event)
        assert event["breadcrumbs"]["values"][0]["message"] == (
            "https://example.com/file?[redacted]"
        )
        client.close()


def test_sentry_scrubs_doubly_encoded_url_from_warning_breadcrumb():
    """Redact signed URLs in warning breadcrumbs after repeated URL encoding."""
    envelopes = []

    class MemoryTransport(Transport):
        """Capture Sentry events without sending them to a server."""

        def capture_envelope(self, envelope):
            """Store the envelope for inspection."""
            envelopes.append(envelope)

    signed_url = "https://example.com/file?signature=SECRET"
    encoded_url = quote(quote(signed_url, safe=""), safe="")
    assert "?" not in encoded_url
    with sentry_sdk.isolation_scope() as scope:
        client = sentry_sdk.Client(
            dsn="https://public@example.com/1",
            transport=MemoryTransport(),
            default_integrations=False,
            integrations=[LoggingIntegration(level=logging.WARNING, event_level=None)],
            before_send=scrub_urls,
            before_breadcrumb=scrub_urls,
        )
        scope.set_client(client)
        try:
            logging.getLogger(__name__).warning("Download failed: %s", encoded_url)
            sentry_sdk.capture_message("Download failed")
            event = envelopes[0].items[0].payload.json
            assert "SECRET" not in json.dumps(event)
            assert event["breadcrumbs"]["values"][0]["message"] == (
                "Download failed: https://example.com/file?[redacted]"
            )
        finally:
            client.close()
