"""Tests for AI job open-in-docs API endpoint."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import AiJobStatusChoices

pytestmark = pytest.mark.django_db


def test_api_ai_jobs_open_in_docs_anonymous_not_allowed():
    """Anonymous users should not be allowed to open docs integration."""
    ai_job = factories.AiFileJobFactory(status=AiJobStatusChoices.SUCCESS)

    response = APIClient().post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_api_ai_jobs_open_in_docs_not_completed_bad_request():
    """Unfinished jobs should be rejected."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        status=AiJobStatusChoices.PENDING,
    )

    client = APIClient()
    client.force_login(user)

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"status": "AI job is not completed yet."}


def test_api_ai_jobs_open_in_docs_missing_docs_id_not_found():
    """Completed jobs without docs id should return not found."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        status=AiJobStatusChoices.SUCCESS,
        docs_app_id=None,
    )

    client = APIClient()
    client.force_login(user)

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"status": "Document not available yet."}


def test_api_ai_jobs_open_in_docs_returns_url_when_docs_id_exists(settings):
    """Completed jobs with docs id should return docs URL."""
    settings.DOCS_BASE_URL = "https://docs.example.com/"

    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        status=AiJobStatusChoices.SUCCESS,
        docs_app_id="existing-doc-id",
    )

    client = APIClient()
    client.force_login(user)

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "doc_url": "https://docs.example.com/docs/existing-doc-id/"
    }
