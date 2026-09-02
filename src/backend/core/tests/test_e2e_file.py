"""End-to-end tests for uploading and validating real media files."""

from pathlib import Path
from unittest.mock import patch

from django.core.files.storage import default_storage

import pytest
from rest_framework.test import APIClient

from core import factories, models
from core.audio import AudioExtractionError
from core.tasks.file import extract_audio

pytestmark = pytest.mark.django_db(transaction=True)

ASSETS_PATH = Path(__file__).parent / "assets"

REAL_MEDIA_SAMPLES = [
    ("audio-sample-android-chrome.webm", 2.346),
    ("audio-sample-android-firefox.ogg", 2.3025),
    ("audio-sample-android.m4a", 1.38),
    ("audio-sample-chromium.webm", 2.7165),
    ("audio-sample-firefox.ogg", 2.0865),
    ("audio-sample-ios-browser.webm", 2.6229),
    ("audio-sample-ios.m4a", 1.3705),
    ("audio-sample-mac-os-safari.webm", 2.3049),
    ("video-sample-visio.mp4", 5.34059),
]
CORRUPTED_MEDIA_SAMPLE = "audio-sample-corrupted.m4a"
NO_AUDIO_MEDIA_SAMPLE = "video-with-no-audio.mp4"


@pytest.mark.parametrize(("asset_name", "expected_duration"), REAL_MEDIA_SAMPLES)
def test_real_media_upload_ended_and_audio_extraction(
    asset_name, expected_duration, settings
):
    """A real browser recording is uploaded, finalized, extracted, and measured."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)
    asset_path = ASSETS_PATH / asset_name

    create_response = client.post(
        "/api/v1.0/files/",
        {
            "title": asset_name,
            "filename": asset_name,
            "duration_seconds": expected_duration,
            "type": models.FileTypeChoices.AUDIO_RECORDING,
        },
        format="json",
    )
    assert create_response.status_code == 201, create_response.json()
    file = models.File.objects.get(id=create_response.json()["id"])

    with asset_path.open("rb") as asset:
        default_storage.save(file.temporary_file_key, asset)

    with (
        patch("core.api.viewsets.queue_audio_extraction") as queue_extraction,
        patch("core.tasks.file.call_transcribe_service.delay") as transcribe,
    ):
        upload_ended_response = client.post(
            f"/api/v1.0/files/{file.id!s}/upload-ended/"
        )

        assert upload_ended_response.status_code == 200, upload_ended_response.json()
        queue_extraction.assert_called_once_with(file.id)

        # Run the queued worker task against the actual S3 object and FFmpeg.
        extract_audio(file.id)

    file.refresh_from_db()
    assert file.upload_state == models.FileUploadStateChoices.READY
    assert (
        file.audio_extraction_state
        == models.FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    assert file.duration_seconds == pytest.approx(expected_duration, abs=0.02)
    assert default_storage.exists(file.audio_file_key)
    transcribe.assert_called_once_with(file.id)


def test_corrupted_media_upload_fails_audio_extraction(settings):
    """A corrupt recording is finalized but never reaches transcription."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)
    asset_path = ASSETS_PATH / CORRUPTED_MEDIA_SAMPLE

    create_response = client.post(
        "/api/v1.0/files/",
        {
            "title": CORRUPTED_MEDIA_SAMPLE,
            "filename": CORRUPTED_MEDIA_SAMPLE,
            "duration_seconds": 10,
            "type": models.FileTypeChoices.AUDIO_RECORDING,
        },
        format="json",
    )
    assert create_response.status_code == 201, create_response.json()
    file = models.File.objects.get(id=create_response.json()["id"])

    with asset_path.open("rb") as asset:
        default_storage.save(file.temporary_file_key, asset)

    with (
        patch("core.api.viewsets.queue_audio_extraction") as queue_extraction,
        patch("core.tasks.file.call_transcribe_service.delay") as transcribe,
    ):
        upload_ended_response = client.post(
            f"/api/v1.0/files/{file.id!s}/upload-ended/"
        )

        assert upload_ended_response.status_code == 200, upload_ended_response.json()
        queue_extraction.assert_called_once_with(file.id)

        with pytest.raises(AudioExtractionError):
            # Run the queued worker task against the actual S3 object and FFmpeg.
            extract_audio(file.id)

    file.refresh_from_db()
    assert file.upload_state == models.FileUploadStateChoices.READY
    assert (
        file.audio_extraction_state
        == models.FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
    )
    assert default_storage.exists(file.file_key)
    assert not default_storage.exists(file.audio_file_key)
    transcribe.assert_not_called()


def test_video_without_audio_fails_extraction_without_raising(settings):
    """A video with no audio stream is rejected without failing the worker task."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)
    asset_path = ASSETS_PATH / NO_AUDIO_MEDIA_SAMPLE

    create_response = client.post(
        "/api/v1.0/files/",
        {
            "title": NO_AUDIO_MEDIA_SAMPLE,
            "filename": NO_AUDIO_MEDIA_SAMPLE,
            "duration_seconds": 2,
            "type": models.FileTypeChoices.AUDIO_RECORDING,
        },
        format="json",
    )
    assert create_response.status_code == 201, create_response.json()
    file = models.File.objects.get(id=create_response.json()["id"])

    with asset_path.open("rb") as asset:
        default_storage.save(file.temporary_file_key, asset)

    with (
        patch("core.api.viewsets.queue_audio_extraction") as queue_extraction,
        patch("core.tasks.file.call_transcribe_service.delay") as transcribe,
    ):
        upload_ended_response = client.post(
            f"/api/v1.0/files/{file.id!s}/upload-ended/"
        )

        assert upload_ended_response.status_code == 200, upload_ended_response.json()
        queue_extraction.assert_called_once_with(file.id)

        # A no-audio media file is a terminal failure, but must not escape the task.
        assert extract_audio(file.id) is None

    file.refresh_from_db()
    assert file.upload_state == models.FileUploadStateChoices.READY
    assert (
        file.audio_extraction_state
        == models.FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED
    )
    assert default_storage.exists(file.file_key)
    assert not default_storage.exists(file.audio_file_key)
    transcribe.assert_not_called()
