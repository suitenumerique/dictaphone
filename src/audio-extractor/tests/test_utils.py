"""Shared media command and transfer utility tests."""

import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from audio_extractor.utils import (
    ProcessingError,
    _download,
    _redact_url,
    _run,
    _upload,
)


def test_upload_uses_signed_put_url_and_ogg_content_type(tmp_path):
    """The converted output is streamed to signed storage as OGG."""
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    response = Mock()
    uploaded = {}

    def capture_upload(url, data, **kwargs):
        uploaded["url"] = url
        uploaded["body"] = data.read()
        uploaded["kwargs"] = kwargs
        return response

    with patch("audio_extractor.utils.requests.put", side_effect=capture_upload) as put:
        _upload("https://storage.test/signed-put", source, 19)

    assert uploaded["url"] == "https://storage.test/signed-put"
    assert uploaded["body"] == b"ogg data"
    assert uploaded["kwargs"]["headers"] == {"Content-Type": "audio/ogg"}
    assert uploaded["kwargs"]["timeout"] == 19
    response.raise_for_status.assert_called_once()
    put.assert_called_once()


def test_upload_sends_acl_header_when_configured(tmp_path):
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    response = Mock()

    with patch("audio_extractor.utils.requests.put", return_value=response) as put:
        _upload(
            "https://storage.test/signed-put",
            source,
            19,
            destination_headers={
                "X-amz-acl": "private",
                "x-amz-server-side-encryption": "AES256",
            },
        )

    assert put.call_args.kwargs["headers"] == {
        "Content-Type": "audio/ogg",
        "X-amz-acl": "private",
        "x-amz-server-side-encryption": "AES256",
    }


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://user:pass@example.test:8443/audio/file?token=secret#fragment",
            "https://example.test:8443/audio/file",
        ),
        (
            "https://[2001:db8::1]:9443/audio/file?signature=secret",
            "https://[2001:db8::1]:9443/audio/file",
        ),
        ("https://example.test/audio/file", "https://example.test/audio/file"),
    ],
)
def test_redact_url_removes_credentials_query_and_fragment(url, expected):
    assert _redact_url(url) == expected


def test_upload_retries_transient_failures_three_times(tmp_path):
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    response = Mock()
    put = Mock(
        side_effect=[
            requests.ConnectionError("temporary outage"),
            requests.Timeout("temporary timeout"),
            requests.ConnectionError("temporary outage"),
            response,
        ]
    )

    with (
        patch("audio_extractor.utils.requests.put", put),
        patch("audio_extractor.utils.time.sleep") as sleep,
    ):
        _upload("https://storage.test/signed-put", source, 19)

    assert put.call_count == 4
    assert sleep.call_count == 3
    response.raise_for_status.assert_called_once()


def test_upload_does_not_retry_client_errors(tmp_path):
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError(
        response=Mock(status_code=403)
    )
    put = Mock(return_value=response)

    with (
        patch("audio_extractor.utils.requests.put", put),
        patch("audio_extractor.utils.time.sleep") as sleep,
        pytest.raises(requests.HTTPError),
    ):
        _upload("https://storage.test/signed-put", source, 19)

    put.assert_called_once()
    sleep.assert_not_called()


def test_download_retries_transient_failures_three_times(tmp_path):
    destination = tmp_path / "source.media"
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"audio"]
    get = Mock(
        side_effect=[
            requests.ConnectionError("temporary outage"),
            requests.Timeout("temporary timeout"),
            requests.ConnectionError("temporary outage"),
            response,
        ]
    )

    with (
        patch("audio_extractor.utils.requests.get", get),
        patch("audio_extractor.utils.time.sleep") as sleep,
    ):
        _download("https://storage.test/signed-get", destination, 19, 100)

    assert get.call_count == 4
    assert sleep.call_count == 3
    assert destination.read_bytes() == b"audio"


def test_media_command_timeout_becomes_processing_error():
    """Media command timeouts are wrapped in a processing error."""
    with (
        patch(
            "audio_extractor.utils.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["ffmpeg"], 17),
        ) as run_command,
        pytest.raises(ProcessingError, match="timed out"),
    ):
        _run(["ffmpeg"], 17)

    assert run_command.call_args.kwargs["timeout"] == 17
