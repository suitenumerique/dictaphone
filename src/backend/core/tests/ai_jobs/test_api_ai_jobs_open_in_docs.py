"""Tests for AI job open-in-docs API endpoint."""

from unittest.mock import Mock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices

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
        type=AiJobTypeChoices.TRANSCRIPT,
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
        type=AiJobTypeChoices.TRANSCRIPT,
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
        type=AiJobTypeChoices.TRANSCRIPT,
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


def test_api_ai_jobs_create_in_docs_anonymous_not_allowed():
    """Anonymous users should not be allowed to create Docs documents."""
    ai_job = factories.AiFileJobFactory(status=AiJobStatusChoices.SUCCESS)

    response = APIClient().post(f"/api/v1.0/ai-jobs/{ai_job.id}/create-in-docs/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_api_ai_jobs_create_in_docs_rejects_unsuccessful_job():
    """Unsuccessful jobs should not create Docs documents."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )
    client = APIClient()
    client.force_login(user)

    with patch("core.api.viewsets.create_document_in_docs") as create_document:
        response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/create-in-docs/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"status": "AI job is not completed yet."}
    create_document.assert_not_called()


def test_api_ai_jobs_create_in_docs_rejects_existing_document():
    """Jobs already associated with a Docs document should be rejected."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        docs_app_id="existing-doc-id",
    )
    client = APIClient()
    client.force_login(user)

    with patch("core.api.viewsets.create_document_in_docs") as create_document:
        response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/create-in-docs/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "docs_app_id": "AI job is already associated with a document."
    }
    create_document.assert_not_called()


@patch("core.tasks.file.AiFileJob.to_markdown")
@patch("core.tasks.file.session.post")
def test_api_ai_jobs_create_in_docs_creates_document_synchronously(
    post, to_markdown, settings
):
    """A successful transcript should synchronously invoke Docs creation."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        docs_app_id=None,
    )
    client = APIClient()
    client.force_login(user)
    settings.DOCS_BASE_URL = "https://docs.example.com/"
    settings.DOCS_SERVER_TO_SERVER_API_KEY = "docs-api-key"

    to_markdown.return_value = "# Transcript"
    docs_response = Mock()
    docs_response.status_code = 201
    docs_response.json.return_value = {"id": "new-doc-id"}
    post.return_value = docs_response

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/create-in-docs/")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == {"doc_url": "https://docs.example.com/docs/new-doc-id/"}
    post.assert_called_once()
    ai_job.refresh_from_db()
    assert ai_job.docs_app_id == "new-doc-id"
