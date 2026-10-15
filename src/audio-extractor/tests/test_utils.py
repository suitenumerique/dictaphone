"""Shared media command and transfer utility tests."""

import subprocess
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from audio_extractor.http_client import configure_session, get_session
from audio_extractor.settings import Settings
from audio_extractor.utils import (
    STDERR_TAIL_BYTES,
    ProcessingError,
    _capture_stderr,
    _download,
    _redact_url,
    _run,
    _upload,
)


def test_upload_uses_signed_put_url_and_ogg_content_type(tmp_path, http_session):
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

    with patch.object(http_session, "put", side_effect=capture_upload) as put:
        _upload(
            "https://storage.test/signed-put",
            source,
            19,
        )

    assert uploaded["url"] == "https://storage.test/signed-put"
    assert uploaded["body"] == b"ogg data"
    assert uploaded["kwargs"]["headers"] == {"Content-Type": "audio/ogg"}
    assert uploaded["kwargs"]["timeout"] == 19
    response.raise_for_status.assert_called_once()
    put.assert_called_once()


def test_upload_sends_acl_header_when_configured(tmp_path, http_session):
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    response = Mock()

    with patch.object(http_session, "put", return_value=response) as put:
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


def test_upload_does_not_replay_transient_failures(tmp_path, http_session):
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    with (
        patch.object(
            http_session, "put", side_effect=requests.ConnectionError("outage")
        ) as put,
        patch("audio_extractor.utils.time.sleep") as sleep,
        pytest.raises(requests.ConnectionError),
    ):
        _upload("https://storage.test/signed-put", source, 19)
    put.assert_called_once()
    sleep.assert_not_called()


def test_upload_does_not_retry_client_errors(tmp_path, http_session):
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError(
        response=Mock(status_code=403)
    )
    put = Mock(return_value=response)

    with (
        patch.object(http_session, "put", put),
        patch("audio_extractor.utils.time.sleep") as sleep,
        pytest.raises(requests.HTTPError),
    ):
        _upload(
            "https://storage.test/signed-put",
            source,
            19,
        )

    put.assert_called_once()
    sleep.assert_not_called()


def test_download_retries_transient_failures_three_times(tmp_path, http_session):
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
        patch.object(http_session, "get", get),
        patch("audio_extractor.utils.time.sleep") as sleep,
    ):
        _download(
            "https://storage.test/signed-get",
            destination,
            19,
            100,
        )

    assert get.call_count == 4
    assert sleep.call_count == 3
    assert destination.read_bytes() == b"audio"


@pytest.mark.parametrize("capture_output", [False, True])
def test_media_command_failure_includes_stderr(capture_output):
    """Actual subprocess stderr reaches the processing error in both modes."""
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('Invalid audio data\\n'); sys.exit(1)",
    ]

    with pytest.raises(
        ProcessingError, match="^Media command failed: Invalid audio data$"
    ) as error:
        _run(command, 17, capture_output=capture_output)

    assert isinstance(error.value.__cause__, subprocess.CalledProcessError)
    assert error.value.__cause__.stderr == "Invalid audio data\n"


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


def test_stderr_capture_stays_bounded_while_reading():
    """Each read discards old diagnostics before requesting further output."""
    tail = bytearray()
    reads = 0

    def read(size):
        nonlocal reads
        assert len(tail) <= STDERR_TAIL_BYTES
        reads += 1
        return b"x" * size if reads <= 1000 else b""

    _capture_stderr(Mock(read1=read), tail)
    assert tail == b"x" * STDERR_TAIL_BYTES


@pytest.mark.parametrize("capture_output", [False, True])
def test_noisy_media_command_retains_only_stderr_tail(capture_output):
    """Large stderr does not block the command or hide its final diagnostic."""
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('x' * 2_000_000 + 'final diagnostic'); "
        "sys.stdout.write('output'); sys.exit(1)",
    ]
    with pytest.raises(ProcessingError, match="final diagnostic$") as error:
        _run(command, 17, capture_output=capture_output)
    assert len(error.value.__cause__.stderr) == STDERR_TAIL_BYTES
    assert error.value.__cause__.stdout == ("output" if capture_output else None)


def test_noisy_media_command_timeout_retains_stderr_tail():
    command = [
        sys.executable,
        "-c",
        "import sys, time; sys.stderr.write('x' * 2_000_000 + 'final diagnostic'); "
        "sys.stderr.flush(); time.sleep(30)",
    ]
    with pytest.raises(ProcessingError, match="final diagnostic$") as error:
        _run(command, 1)
    assert isinstance(error.value.__cause__, subprocess.TimeoutExpired)
    assert len(error.value.__cause__.stderr) == STDERR_TAIL_BYTES


def test_gateway_routes_storage_only_and_preserves_signed_headers(
    tmp_path, http_session
):
    configure_session(
        Settings(
            api_url="https://api.example.test/api/internal/v1.0",
            token="worker-token-for-tests-0123456789",
            s3_gateway_url="http://s3-gateway:8080/proxy",
        )
    )
    session = get_session()
    source = tmp_path / "audio.ogg"
    source.write_bytes(b"ogg data")
    url = "https://storage.test/files/a?X-Amz-Signature=a%2Bb"
    response = Mock()
    with patch.object(session, "put", return_value=response) as put:
        _upload(
            url, source, 19, {"Content-Type": "audio/ogg", "x-amz-meta-test": "signed"}
        )
    assert put.call_args.args == ("http://s3-gateway:8080/proxy",)
    assert put.call_args.kwargs["headers"] == {
        "Content-Type": "audio/ogg",
        "x-amz-meta-test": "signed",
        "X-Target-URL": url,
        "Content-Length": "8",
    }
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"audio"]
    with patch.object(session, "get", return_value=response) as get:
        _download(url, tmp_path / "download", 19, 100)
    assert get.call_args.args == ("http://s3-gateway:8080/proxy",)
    assert get.call_args.kwargs["headers"] == {"X-Target-URL": url}
    assert get.call_args.kwargs["allow_redirects"] is False
    assert session.headers["User-Agent"].startswith("dictaphone-audio-extractor")
