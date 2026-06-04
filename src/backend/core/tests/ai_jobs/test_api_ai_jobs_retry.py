"""Tests for AI job retry API endpoint."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices, FileLifecycleStateChoices

pytestmark = pytest.mark.django_db


def test_api_ai_jobs_retry_anonymous_not_allowed():
    """Anonymous users should not be allowed to retry AI jobs."""
    ai_job = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)

    response = APIClient().post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "en"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


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
    ai_job.file.save(update_fields=["created_at"])

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
    )
    retried_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        language="fr",
        file=ai_job.file,
    )
    mock_task.return_value = retried_job.id

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "fr"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["id"] == str(retried_job.id)
    assert response.json()["language"] == "fr"
    mock_task.assert_called_once_with(ai_job.file_id, language="fr")


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_language_change_allowed(mock_task):
    """Successful transcript should be retriable when changing language."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        language="fr",
        file__creator=user,
    )
    retried_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        language="en",
        file=ai_job.file,
    )
    mock_task.return_value = retried_job.id

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/ai-jobs/{ai_job.id}/retry/",
        {"language": "en"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["id"] == str(retried_job.id)
    assert response.json()["language"] == "en"
    mock_task.assert_called_once_with(ai_job.file_id, language="en")


@patch("core.api.viewsets.call_transcribe_service")
def test_api_ai_jobs_retry_task_returns_unknown_job_id(mock_task):
    """Retry should fail with 404 when returned job id does not exist."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
        language="fr",
        file__creator=user,
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
