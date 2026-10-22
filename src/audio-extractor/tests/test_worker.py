"""Task processing and polling tests."""

from unittest.mock import Mock, patch

import pytest
import requests

from audio_extractor.api_models import ValidationJob
from audio_extractor.http_client import configure_session
from audio_extractor.utils import ProcessingError
from audio_extractor.worker import (
    _log_job_failure,
    process_transcoding_job,
    process_validation_job,
    run,
)


def test_transcoding_success_uploads_and_reports_duration(config, task, http_session):
    response = Mock()

    def download(_url, destination, *_args, **_kwargs):
        destination.write_bytes(b"source")

    def convert(_source, output, *_args, **_kwargs):
        output.write_bytes(b"converted")
        return 12.5

    with (
        patch(
            "audio_extractor.worker._download", side_effect=download
        ) as download_mock,
        patch("audio_extractor.worker._convert", side_effect=convert) as convert_mock,
        patch("audio_extractor.worker._upload") as upload,
        patch.object(http_session, "post", return_value=response) as post,
    ):
        process_transcoding_job(config, task)

    download_mock.assert_called_once()
    convert_mock.assert_called_once()
    upload.assert_called_once()
    assert upload.call_args.args[0] == task.destination_url
    assert upload.call_args.kwargs["destination_headers"] == {}
    post.assert_called_once()
    assert post.call_args.args[0] == (
        "https://api.example.test/api/internal/v1.0/audio-jobs/transcoding/complete"
    )
    payload = post.call_args.kwargs["json"]
    assert payload["id"] == "job-123"
    assert payload["status"] == "success"
    assert payload["duration_seconds"] == 12.5
    metrics = payload["metadata"]
    assert metrics["download_file_size_bytes"] == 6
    assert metrics["result_file_size_bytes"] == 9
    assert metrics["download_seconds"] >= 0
    assert metrics["convert_seconds"] >= 0
    assert metrics["upload_seconds"] >= 0
    assert post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer worker-token-for-tests-0123456789"
    }
    assert http_session.headers["User-Agent"] == config.user_agent
    assert post.call_args.kwargs["timeout"] == 30
    response.raise_for_status.assert_called_once()


def test_transcoding_worker_passes_job_acl_to_upload(config, task, http_session):
    task = task.model_copy(
        update={
            "destination_headers": {
                "X-amz-acl": "private",
                "x-amz-server-side-encryption": "AES256",
            }
        }
    )

    def download(_url, destination, *_args, **_kwargs):
        destination.write_bytes(b"source")

    def convert(_source, output, *_args, **_kwargs):
        output.write_bytes(b"converted")
        return 12.5

    with (
        patch("audio_extractor.worker._download", side_effect=download),
        patch("audio_extractor.worker._convert", side_effect=convert),
        patch("audio_extractor.worker._upload") as upload,
        patch.object(http_session, "post"),
    ):
        process_transcoding_job(config, task)

    assert upload.call_args.kwargs["destination_headers"] == {
        "X-amz-acl": "private",
        "x-amz-server-side-encryption": "AES256",
    }


def test_validation_mode_validates_without_upload_or_duration(
    config, task, http_session
):
    config = config.model_copy(update={"mode": "validation"})
    task = ValidationJob(
        job_kind="validation",
        id=task.id,
        source_url=task.source_url,
        expires_at=task.expires_at,
    )
    response = Mock()
    http_session = configure_session(config)

    def download(_url, destination, *_args, **_kwargs):
        destination.write_bytes(b"source")

    with (
        patch("audio_extractor.worker._download", side_effect=download),
        patch("audio_extractor.worker._validate_opus") as validate,
        patch("audio_extractor.worker._upload") as upload,
        patch.object(http_session, "post", return_value=response) as post,
    ):
        process_validation_job(config, task)

    validate.assert_called_once()
    upload.assert_not_called()
    assert post.call_args.args[0] == (
        "https://api.example.test/api/internal/v1.0/audio-jobs/validation/complete"
    )
    payload = post.call_args.kwargs["json"]
    assert payload["id"] == "job-123"
    assert payload["status"] == "success"
    assert payload["metadata"]["download_file_size_bytes"] == 6
    assert payload["metadata"]["download_seconds"] >= 0
    assert payload["metadata"]["validate_seconds"] >= 0
    assert post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer worker-token-for-tests-0123456789"
    }
    assert (
        http_session.headers["User-Agent"]
        == config.model_copy(update={"mode": "validation"}).user_agent
    )


def test_processing_error_is_reported_and_logged_without_signed_urls(
    config, task, caplog, http_session
):
    with (
        patch(
            "audio_extractor.worker._download",
            side_effect=ProcessingError("bad media"),
        ),
        patch.object(http_session, "post") as post,
    ):
        process_transcoding_job(config, task)

    assert post.call_args.args[0] == (
        "https://api.example.test/api/internal/v1.0/audio-jobs/transcoding/complete"
    )
    payload = post.call_args.kwargs["json"]
    assert payload["id"] == "job-123"
    assert payload["status"] == "failure"
    assert payload["error"] == "bad media"
    assert payload["metadata"]["download_seconds"] >= 0
    assert f"{task.source_url.split('?', maxsplit=1)[0]}?[redacted]" in caplog.text
    assert f"{task.destination_url.split('?', maxsplit=1)[0]}?[redacted]" in caplog.text
    assert "signature=unchanged" not in caplog.text


def test_exception_urls_are_redacted_in_logs(task, caplog):
    _log_job_failure(
        "Transcoding",
        task.id,
        task.source_url,
        RuntimeError(f"download failed for {task.source_url}"),
        task.destination_url,
    )

    assert f"{task.source_url.split('?', maxsplit=1)[0]}?[redacted]" in caplog.text
    assert "signature=unchanged" not in caplog.text


@pytest.mark.parametrize(
    "url",
    [
        "/audio/file?signature=unchanged",
        "/other/file?token=secret",
        "https://other.test/file?token=secret",
    ],
)
def test_exception_queries_leave_redaction_marker(task, caplog, url):
    _log_job_failure(
        "Transcoding", task.id, task.source_url, RuntimeError(f"failed: {url}")
    )

    assert f"failed: {url.split('?', maxsplit=1)[0]}?[redacted]" in caplog.text
    assert "signature=unchanged" not in caplog.text
    assert "token=secret" not in caplog.text


def test_source_download_failure_is_reported_to_callback(config, task, http_session):
    """A storage transfer outage is reported as a failed task."""
    with (
        patch(
            "audio_extractor.worker._download",
            side_effect=requests.ConnectionError("temporary storage outage"),
        ),
        patch.object(http_session, "post") as post,
    ):
        process_transcoding_job(config, task)

    payload = post.call_args.kwargs["json"]
    assert payload["id"] == "job-123"
    assert payload["status"] == "failure"
    assert payload["error"] == "temporary storage outage"
    assert payload["metadata"]["download_seconds"] >= 0


def test_run_cleans_work_directory_and_sends_worker_bearer(lifecycle, tmp_path):
    config, _, _ = lifecycle
    stale_file = config.work_dir / "stale"
    stale_file.write_text("old task")
    external_directory = tmp_path.parent / "external"
    external_directory.mkdir()
    outside_file = external_directory / "outside"
    outside_file.write_text("keep")
    stale_link = config.work_dir / "link"
    stale_link.symlink_to(external_directory, target_is_directory=True)
    response = Mock(status_code=204)
    with patch("requests.Session.get", return_value=response) as get:
        run(config)

    assert not stale_file.exists()
    assert not stale_link.exists()
    assert outside_file.read_text() == "keep"
    get.assert_called_once_with(
        "https://api.example.test/api/internal/v1.0/audio-jobs/transcoding/next",
        headers={
            "Authorization": "Bearer worker-token-for-tests-0123456789",
        },
        timeout=30,
    )


def test_validation_worker_polls_validation_route(lifecycle):
    config, _, _ = lifecycle
    config = config.model_copy(update={"mode": "validation"})
    response = Mock(status_code=204)
    with patch("requests.Session.get", return_value=response) as get:
        run(config)

    assert (
        get.call_args.args[0]
        == "https://api.example.test/api/internal/v1.0/audio-jobs/validation/next"
    )
    assert get.call_args.kwargs["headers"] == {
        "Authorization": "Bearer worker-token-for-tests-0123456789"
    }


def test_run_processes_a_returned_task(lifecycle, task):
    config, _, _ = lifecycle
    response = Mock(status_code=200)
    response.json.return_value = task.model_dump()
    with (
        patch("requests.Session.get", return_value=response),
        patch("audio_extractor.supervisor._process_attempt") as process,
    ):
        process.side_effect = lambda *_args: lifecycle[2].set()
        run(config)

    assert process.call_count == 1
    assert process.call_args.args[:2] == (config, task)
