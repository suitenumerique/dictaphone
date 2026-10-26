"""Tests for AI job retry API endpoint."""

import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone

import pytest
import requests
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AiJobTypeChoices,
    FileAudioExtractionStateChoices,
    FileLifecycleStateChoices,
    FileTypeChoices,
)

pytestmark = pytest.mark.django_db


def test_api_ai_jobs_retry_anonymous_not_allowed():
    """Anonymous users should not be allowed to retry AI jobs."""
    ai_job = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)

    response = APIClient().post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "en"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize("used_seconds,allowed", [(0, True), (3600, False)])
@patch("core.tasks.file.session.post")
def test_api_ai_jobs_retry_audio_quota(post, settings, used_seconds, allowed):
    """Retry uses the same duration quota and returns a persisted failure reason."""
    settings.RATE_LIMIT_AI_TRANSCRIPTION_AUDIO_HOURS_PER_24H = 1
    user = factories.UserFactory()
    old_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
        file__duration_seconds=120,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    factories.TranscriptionUsageFactory(
        user=user,
        submitted_at=timezone.now(),
        duration_seconds=used_seconds,
    )
    post.return_value.headers = {}
    post.return_value.iter_content.return_value = [
        json.dumps({"job_id": "quota-retry"}).encode()
    ]
    client = APIClient()
    client.force_login(user)

    response = client.post(f"/api/v1.0/ai-jobs/{old_job.pk}/retry/", {"language": "en"})

    assert response.status_code == 201
    new_job = AiFileJob.objects.get(pk=response.json()["id"])
    assert new_job.status == ("pending" if allowed else "failed")
    reason = "" if allowed else "RATE_LIMIT_TRANSCRIPTION_EXCEEDED"
    assert new_job.failure_reason == reason
    assert response.json()["failure_reason"] == reason
    assert post.call_count == int(allowed)
    assert (
        client.get(f"/api/v1.0/ai-jobs/{new_job.pk}/").json()["failure_reason"]
        == reason
    )
    file_data = client.get(f"/api/v1.0/files/{old_job.file_id}/").json()
    returned_job = next(
        job for job in file_data["ai_jobs"] if job["id"] == str(new_job.pk)
    )
    assert returned_job["failure_reason"] == reason


def test_api_ai_jobs_retry_non_owner_not_found():
    """Users should not retry transcript jobs they don't own."""
    ai_job = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)
    other_user = factories.UserFactory()
    client = APIClient()
    client.force_login(other_user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "en"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_api_ai_jobs_retry_file_past_deadline_not_found(settings):
    """Retry should not be possible when file is past API availability deadline."""
    settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS = 10
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        file__creator=user,
    )
    ai_job.file.created_at = ai_job.file.created_at - timedelta(days=11)
    ai_job.file.file_auto_hard_delete_at = timezone.now() - timedelta(days=1)
    ai_job.file.save(update_fields=["created_at", "file_auto_hard_delete_at"])

    client = APIClient()
    client.force_login(user)
    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "en"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_api_ai_jobs_retry_invalid_language_bad_request():
    """Language must be a valid ISO 639-1 code."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
    )
    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "zzz"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "language": ['"zzz" is not a valid choice.'],
    }


def test_api_ai_jobs_retry_pending_bad_request():
    """Language must be a valid ISO 639-1 code."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
        file__creator=user,
    )
    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "state": "Cannot retry when there is a pending job already.",
    }


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_non_transcript_bad_request(mock_task):
    """Only transcript jobs should be retriable."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
    )
    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "en"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"type": "Only transcript jobs can be retried."}
    mock_task.assert_not_called()


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_same_language_requires_failure(mock_task):
    """Retry should be rejected for successful transcript with same language."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        language="fr",
        file__creator=user,
    )
    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "language": ("Cannot retry with the same language when job is successful.")
    }
    mock_task.assert_not_called()


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_failed_transcript_allowed(mock_task):
    """Failed transcript should be retriable with same language."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        language="fr",
        file__creator=user,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    mock_task.side_effect = lambda job_id: job_id

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    retried_job = AiFileJob.objects.get(pk=response.json()["id"])
    assert retried_job.pk != ai_job.pk
    assert response.json()["id"] == str(retried_job.id)
    assert response.json()["language"] == "fr"
    assert retried_job.status == AiJobStatusChoices.PENDING
    assert retried_job.validated_audio_job_id == ai_job.file.latest_audio_job.id
    assert ai_job.file.ai_jobs.count() == 2
    mock_task.assert_called_once_with(retried_job.id)


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_language_change_allowed(mock_task):
    """Successful transcript should be retriable when changing language."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        language="fr",
        file__creator=user,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    mock_task.side_effect = lambda job_id: job_id

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "en"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    retried_job = AiFileJob.objects.get(pk=response.json()["id"])
    assert retried_job.pk != ai_job.pk
    assert response.json()["id"] == str(retried_job.id)
    assert response.json()["language"] == "en"
    assert retried_job.validated_audio_job_id == ai_job.file.latest_audio_job.id
    mock_task.assert_called_once_with(retried_job.id)


@patch("core.api.viewsets.call_transcribe_service.apply_async")
@patch("core.tasks.file.session.post", side_effect=requests.ConnectionError("offline"))
def test_api_ai_jobs_retry_transient_failure_queues_reserved_job(
    mock_post, mock_publish, django_capture_on_commit_callbacks, settings
):
    """Synchronous submission failures continue on the same reserved job in Celery."""
    user = factories.UserFactory()
    old_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    client = APIClient()
    client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"/api/v1.0/ai-jobs/{old_job.pk}/retry/", {"language": "en"}
        )
        mock_publish.assert_not_called()

    assert response.status_code == status.HTTP_201_CREATED
    job = AiFileJob.objects.get(pk=response.json()["id"])
    assert old_job.file.ai_jobs.count() == 2
    assert job.status == AiJobStatusChoices.PENDING
    assert job.remote_job_id is None
    assert job.language == "en"
    mock_post.assert_called_once()
    mock_publish.assert_called_once_with(
        args=[job.pk], retries=1, countdown=settings.CELERY_TASK_RETRY_BACKOFF_SECONDS
    )


@pytest.mark.parametrize("failure", ["http_error", "invalid_job_id", "missing_audio"])
@patch("core.api.viewsets.call_transcribe_service.apply_async")
@patch("core.tasks.file.session.post")
def test_api_ai_jobs_retry_returns_permanently_failed_job(
    mock_post, mock_publish, failure
):
    """Terminal submission errors return the reserved failed job without retrying."""
    old_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    if failure == "http_error":
        response = requests.Response()
        response.status_code = 400
        mock_post.return_value.raise_for_status.side_effect = requests.HTTPError(
            "invalid request", response=response
        )
    elif failure == "invalid_job_id":
        mock_post.return_value.headers = {}
        mock_post.return_value.iter_content.return_value = [
            json.dumps({"job_id": ""}).encode()
        ]

    client = APIClient()
    client.force_login(old_job.file.creator)

    if failure == "missing_audio":
        # Audio can disappear after reservation and before the task validates it.
        with patch("core.tasks.file._validate_transcription_audio") as validate:
            validate.side_effect = [None, ValueError("audio disappeared")]
            response = client.post(
                f"/api/v1.0/ai-jobs/{old_job.pk}/retry/", {"language": "en"}
            )
    else:
        response = client.post(
            f"/api/v1.0/ai-jobs/{old_job.pk}/retry/", {"language": "en"}
        )

    assert response.status_code == status.HTTP_201_CREATED
    job = AiFileJob.objects.get(pk=response.json()["id"])
    assert job.pk != old_job.pk
    assert job.status == AiJobStatusChoices.FAILED
    assert response.json()["status"] == AiJobStatusChoices.FAILED
    assert job.remote_job_id is None
    assert old_job.file.ai_jobs.count() == 2
    mock_publish.assert_not_called()


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_task_returns_unknown_job_id(mock_task):
    """Retry should fail with 404 when returned job id does not exist."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        language="fr",
        file__creator=user,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    mock_task.return_value = uuid4()

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_file_not_active_bad_request(mock_task):
    """Retry should return 400 when file is not in active lifecycle state."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
    )
    ai_job.file.lifecycle_state = FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
    ai_job.file.save(update_fields=["lifecycle_state"])

    client = APIClient()
    client.force_login(user)
    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "state": "Cannot retry when file is not in active state.",
    }
    mock_task.assert_not_called()


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_audio_extraction_failed_bad_request(mock_task):
    """A failed audio extraction must block transcript retries."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
        file__audio_extraction_state=FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED,
    )
    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "state": "Cannot retry when audio extraction has failed."
    }
    mock_task.assert_not_called()


@patch("core.api.viewsets.call_transcribe_service")
@pytest.mark.parametrize(
    "audio_state",
    [
        FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION,
        FileAudioExtractionStateChoices.EXTRACTING_AUDIO,
    ],
)
def test_api_ai_jobs_retry_requires_validated_audio(mock_task, audio_state):
    """Retry cannot create an AI job while audio processing is pending."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
        file__duration_seconds=120,
        file__audio_extraction_state=audio_state,
    )
    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.json()
    assert response.json() == {
        "state": "Cannot retry before audio validation has succeeded."
    }
    assert ai_job.file.ai_jobs.count() == 1
    mock_task.assert_not_called()


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_file_duration_above_limit_bad_request(mock_task, settings):
    """Retry should return 400 when file duration is above allowed max duration."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    max_duration_seconds = settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"][
        "max_duration_seconds"
    ]
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        file__creator=user,
        file__type=FileTypeChoices.AUDIO_RECORDING,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
        file__duration_seconds=max_duration_seconds + 1,
    )

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "file": "Cannot retry the file duration is above the allowed max duration.",
    }
    mock_task.assert_not_called()
