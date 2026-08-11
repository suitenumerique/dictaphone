"""Tests for validated audio extraction and its task state machine."""

import json
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest
from celery.exceptions import Retry

from core import analytics, factories
from core.audio import (
    AudioExtractionError,
    AudioExtractionRetryableError,
    extract_audio_to_storage,
)
from core.models import (
    AiJobStatusChoices,
    FileAudioExtractionStateChoices,
)
from core.storage import get_storage_for_file
from core.tasks.file import (
    call_transcribe_service,
    extract_audio,
    queue_audio_extraction,
)

pytestmark = pytest.mark.django_db


def test_extract_audio_to_storage_streams_source_and_uploads_high_quality_ogg():
    """Conversion should use disk-backed files and preserve channel information."""
    file = factories.FileFactory(filename="recording.webm")
    storage = get_storage_for_file(file)
    captured_commands = []

    def run(command, **kwargs):
        captured_commands.append(command)
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"valid ogg")
            return CompletedProcess(command, 0, stdout=None, stderr="")
        return CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "audio",
                            "codec_name": "opus",
                            "channels": 2,
                            "sample_rate": "48000",
                        }
                    ],
                    "format": {"duration": "12.5"},
                }
            ),
            stderr="",
        )

    with (
        patch.object(storage, "open", return_value=BytesIO(b"source")),
        patch("core.audio.subprocess.run", side_effect=run),
        patch.object(storage.connection.meta.client, "upload_file") as upload,
    ):
        duration = extract_audio_to_storage(file)

    assert duration == 12.5
    ffmpeg_command = next(
        command for command in captured_commands if command[0] == "ffmpeg"
    )
    assert ffmpeg_command[ffmpeg_command.index("-b:a") + 1] == "256k"
    assert "-ac" not in ffmpeg_command
    upload.assert_called_once()
    assert upload.call_args.args[2] == file.audio_file_key
    assert upload.call_args.kwargs["ExtraArgs"] == {"ContentType": "audio/ogg"}


def test_extract_audio_to_storage_classifies_storage_download_errors_as_retryable():
    """An object-storage download failure must be retried, not poison the file."""
    file = factories.FileFactory(filename="recording.webm")
    storage = get_storage_for_file(file)

    with patch.object(storage, "open", side_effect=RuntimeError("temporary S3 outage")):
        with pytest.raises(AudioExtractionRetryableError, match="downloaded"):
            extract_audio_to_storage(file)


@patch("core.tasks.file.call_transcribe_service.delay")
@patch("core.tasks.file.extract_audio_to_storage", return_value=42.25)
def test_extract_audio_marks_done_and_queues_transcription(
    mock_extract, mock_transcribe
):
    """Successful extraction persists the real duration before transcription."""
    file = factories.FileFactory(upload_bytes=b"source")

    extract_audio(file.id)

    file.refresh_from_db()
    assert (
        file.audio_extraction_state == FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    assert file.duration_seconds == 42.25
    mock_extract.assert_called_once_with(file)
    mock_transcribe.assert_called_once_with(file.id)


def test_extract_audio_records_success_analytics_and_warns_on_duration_difference(
    caplog,
):
    """Successful extraction records timing and flags suspicious duration changes."""
    file = factories.FileFactory(upload_bytes=b"source", duration_seconds=100)

    with (
        patch("core.tasks.file.extract_audio_to_storage", return_value=120),
        patch("core.tasks.file.call_transcribe_service.delay"),
        patch("core.tasks.file.monotonic", side_effect=[10, 14]),
        patch("core.tasks.file.analytics.capture_event") as capture_event,
    ):
        extract_audio(file.id)

    assert "Suspicious audio duration difference" in caplog.text
    capture_event.assert_called_once_with(
        analytics.EventName.AUDIO_EXTRACTION_SUCCESS,
        user=file.creator,
        properties={
            "preprocessing_time_seconds": 4,
            "file_id": file.id,
            "input_file_type": file.type,
            "audio_duration_seconds": 120,
        },
    )


@patch("core.tasks.file.call_transcribe_service.delay")
@patch(
    "core.tasks.file.extract_audio_to_storage",
    side_effect=AudioExtractionError("invalid audio"),
)
def test_extract_audio_marks_failed_and_does_not_transcribe(
    mock_extract, mock_transcribe
):
    """Permanent conversion failures are terminal and never reach the AI service."""
    file = factories.FileFactory(upload_bytes=b"invalid")
    storage = get_storage_for_file(file)
    storage.save(file.audio_file_key, BytesIO(b"stale output"))

    with pytest.raises(AudioExtractionError, match="invalid audio"):
        extract_audio(file.id)

    file.refresh_from_db()
    assert (
        file.audio_extraction_state
        == FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
    )
    assert not storage.exists(file.audio_file_key)
    mock_extract.assert_called_once_with(file)
    mock_transcribe.assert_not_called()


def test_extract_audio_records_failure_analytics():
    """Failed extraction records timing, context, and the exception details."""
    file = factories.FileFactory(upload_bytes=b"invalid")

    with (
        patch(
            "core.tasks.file.extract_audio_to_storage",
            side_effect=AudioExtractionError("invalid audio"),
        ),
        patch("core.tasks.file.monotonic", side_effect=[10, 13]),
        patch("core.tasks.file.analytics.capture_event") as capture_event,
        pytest.raises(AudioExtractionError),
    ):
        extract_audio(file.id)

    capture_event.assert_called_once_with(
        analytics.EventName.AUDIO_EXTRACTION_FAILURE,
        user=file.creator,
        properties={
            "preprocessing_time_seconds": 3,
            "file_id": file.id,
            "input_file_type": file.type,
            "error_type": "AudioExtractionError",
            "error_message": "invalid audio",
            "retryable": False,
        },
    )


@patch("core.tasks.file.call_transcribe_service.delay")
@patch("core.tasks.file.extract_audio_to_storage", return_value=8.5)
def test_extract_audio_rebuilds_missing_done_output(mock_extract, mock_transcribe):
    """A stale done state is repaired when its S3 object is missing."""
    file = factories.FileFactory(
        upload_bytes=b"source",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    get_storage_for_file(file).delete(file.audio_file_key)

    extract_audio(file.id)

    file.refresh_from_db()
    assert (
        file.audio_extraction_state == FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    assert file.duration_seconds == 8.5
    mock_extract.assert_called_once_with(file)
    mock_transcribe.assert_called_once_with(file.id)


@patch("core.tasks.file.extract_audio_to_storage")
def test_extract_audio_does_not_retry_terminal_failure(mock_extract):
    """A terminal extraction failure cannot be silently retried by the worker."""
    file = factories.FileFactory(
        audio_extraction_state=FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
    )

    extract_audio(file.id)

    mock_extract.assert_not_called()


@patch(
    "core.tasks.file.extract_audio_to_storage",
    side_effect=AudioExtractionRetryableError("temporary S3 failure"),
)
def test_extract_audio_retries_transient_failure(mock_extract):
    """Infrastructure failures retry without marking a valid file as bad."""
    file = factories.FileFactory(upload_bytes=b"source")

    with (
        patch.object(extract_audio, "retry", side_effect=Retry()) as retry,
        patch("core.tasks.file.monotonic", side_effect=[10, 12]),
        patch("core.tasks.file.analytics.capture_event") as capture_event,
    ):
        with pytest.raises(Retry):
            extract_audio(file.id)

    file.refresh_from_db()
    assert (
        file.audio_extraction_state
        == FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
    )
    assert extract_audio.autoretry_for == (AudioExtractionRetryableError,)
    retry.assert_called_once()
    assert retry.call_args.kwargs["max_retries"] > 0
    capture_event.assert_called_once_with(
        analytics.EventName.AUDIO_EXTRACTION_FAILURE,
        user=file.creator,
        properties={
            "preprocessing_time_seconds": 2,
            "file_id": file.id,
            "input_file_type": file.type,
            "error_type": "AudioExtractionRetryableError",
            "error_message": "temporary S3 failure",
            "retryable": True,
        },
    )
    mock_extract.assert_called_once_with(file)


@patch("core.tasks.file.queue_audio_extraction")
def test_call_transcribe_service_queues_pending_extraction(mock_queue, settings):
    """Legacy files are extracted lazily when transcription is requested."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False
    file = factories.FileFactory(upload_bytes=b"source")

    job_id = call_transcribe_service(file.id, language="en")

    job = file.ai_jobs.get(id=job_id)
    assert job.status == AiJobStatusChoices.PENDING
    mock_queue.assert_called_once_with(
        file.id,
        ai_job_id=job.id,
        language="en",
    )


@patch("core.tasks.file.queue_audio_extraction")
def test_call_transcribe_service_queues_missing_done_output(mock_queue, settings):
    """A missing object is treated as not extracted even when state is done."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False
    file = factories.FileFactory(
        upload_bytes=b"source",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    get_storage_for_file(file).delete(file.audio_file_key)

    job_id = call_transcribe_service(file.id, language="en")

    assert file.ai_jobs.get(id=job_id).status == AiJobStatusChoices.PENDING
    mock_queue.assert_called_once_with(
        file.id,
        ai_job_id=job_id,
        language="en",
    )


@patch("core.tasks.file.extract_audio.apply_async")
def test_queue_audio_extraction_uses_dedicated_queue(mock_apply_async):
    """Extraction jobs must be routed to the dedicated audio worker queue."""
    queue_audio_extraction("file-id", ai_job_id="job-id", language="fr")

    mock_apply_async.assert_called_once_with(
        args=["file-id"],
        kwargs={"ai_job_id": "job-id", "language": "fr"},
        queue="dictaphone-audio",
    )
