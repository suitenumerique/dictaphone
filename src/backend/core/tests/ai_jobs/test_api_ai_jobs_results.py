"""Tests for AI job summary/transcript API endpoints."""

from io import BytesIO

from django.core.files.storage import default_storage

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices

pytestmark = pytest.mark.django_db


def test_api_ai_jobs_transcript_anonymous_not_allowed():
    """Anonymous users should not be allowed to retrieve transcript results."""
    ai_job = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)

    response = APIClient().get(f"/api/v1.0/ai-jobs/{ai_job.id}/transcript/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_api_ai_jobs_transcript_get_own():
    """Authenticated user should retrieve own transcript result."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
    )
    default_storage.save(
        ai_job.key,
        BytesIO(b'{"segments": []}'),
    )

    client = APIClient()
    client.force_login(user)
    response = client.get(f"/api/v1.0/ai-jobs/{ai_job.id}/transcript/")

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"].startswith("application/json")
    assert response.content == b'{"segments": []}'


def test_api_ai_jobs_summary_get_own():
    """Authenticated user should retrieve own summary result."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.SUCCESS,
    )
    default_storage.save(
        ai_job.key,
        BytesIO(b"Summary content"),
    )

    client = APIClient()
    client.force_login(user)
    response = client.get(f"/api/v1.0/ai-jobs/{ai_job.id}/summary/")

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"].startswith("text/plain")
    assert response.content == b"Summary content"


def test_api_ai_jobs_transcript_wrong_type_not_found():
    """Transcript route should return 404 when AI job is not a transcript."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.SUCCESS,
    )
    client = APIClient()
    client.force_login(user)

    response = client.get(f"/api/v1.0/ai-jobs/{ai_job.id}/transcript/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_api_ai_jobs_summary_not_completed_bad_request():
    """Summary route should reject unfinished jobs."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    )
    client = APIClient()
    client.force_login(user)

    response = client.get(f"/api/v1.0/ai-jobs/{ai_job.id}/summary/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_api_ai_jobs_summary_non_owner_not_found():
    """Users should not access summary results for AI jobs they do not own."""
    owner = factories.UserFactory()
    other_user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=owner,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.SUCCESS,
    )
    client = APIClient()
    client.force_login(other_user)

    response = client.get(f"/api/v1.0/ai-jobs/{ai_job.id}/summary/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
