"""Tests for AI job open-in-docs API endpoint."""

import time
from unittest.mock import Mock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices

pytestmark = pytest.mark.django_db


def _set_oidc_session(client, access_token="access-token"):
    """Populate OIDC session keys needed by the refresh decorator."""
    session = client.session
    session["oidc_access_token"] = access_token
    session["oidc_id_token_expiration"] = time.time() + 3600
    session.save()


def test_api_ai_jobs_open_in_docs_anonymous_not_allowed():
    """Anonymous users should not be allowed to open docs integration."""
    ai_job = factories.AiFileJobFactory(status=AiJobStatusChoices.SUCCESS)

    response = APIClient().post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_api_ai_jobs_open_in_docs_missing_access_token():
    """Authenticated users without OIDC access token should be rejected."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        status=AiJobStatusChoices.SUCCESS,
    )

    client = APIClient()
    client.force_login(user)
    session = client.session
    session["oidc_id_token_expiration"] = time.time() + 3600
    session.save()

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"status": "User is not authenticated."}


def test_api_ai_jobs_open_in_docs_not_completed_bad_request():
    """Unfinished jobs should be rejected."""
    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        status=AiJobStatusChoices.PENDING,
    )

    client = APIClient()
    client.force_login(user)
    _set_oidc_session(client)

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"status": "AI job is not completed yet."}


@patch("core.api.viewsets.requests.post")
@patch("core.api.viewsets.AiFileJob.to_markdown")
def test_api_ai_jobs_open_in_docs_create_document(
    mock_to_markdown, mock_post, settings
):
    """A new docs document should be created when no docs id exists yet."""
    settings.DOCS_BASE_URL = "https://docs.example.com/"

    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        docs_app_id=None,
        file__title="Meeting title",
    )

    mock_to_markdown.return_value = "# Transcription"
    post_response = Mock()
    post_response.raise_for_status.return_value = None
    post_response.json.return_value = {"id": "new-doc-id"}
    mock_post.return_value = post_response

    client = APIClient()
    client.force_login(user)
    _set_oidc_session(client, access_token="token-123")

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"doc_url": "https://docs.example.com/docs/new-doc-id/"}

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer token-123"}
    assert kwargs["timeout"] == 10

    args, _ = mock_post.call_args
    file_tuple = args[1]["file"]
    assert file_tuple[0] == "Meeting title - Transcription.md"
    assert file_tuple[1] == b"# Transcription"
    assert file_tuple[2] == "text/markdown"

    ai_job.refresh_from_db()
    assert ai_job.docs_app_id == "new-doc-id"


@patch("core.api.viewsets.requests.post")
@patch("core.api.viewsets.requests.get")
def test_api_ai_jobs_open_in_docs_reuse_existing_document(
    mock_get, mock_post, settings
):
    """Existing docs document should be reused when it still exists."""
    settings.DOCS_BASE_URL = "https://docs.example.com/"

    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        status=AiJobStatusChoices.SUCCESS,
        docs_app_id="existing-doc-id",
    )

    get_response = Mock()
    get_response.status_code = 200
    mock_get.return_value = get_response

    client = APIClient()
    client.force_login(user)
    _set_oidc_session(client, access_token="token-xyz")

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "doc_url": "https://docs.example.com/docs/existing-doc-id/"
    }

    mock_get.assert_called_once_with(
        "https://docs.example.com/external_api/v1.0/documents/existing-doc-id/",
        headers={"Authorization": "Bearer token-xyz"},
        timeout=10,
    )
    mock_post.assert_not_called()


@patch("core.api.viewsets.requests.post")
@patch("core.api.viewsets.requests.get")
@patch("core.api.viewsets.AiFileJob.to_markdown")
def test_api_ai_jobs_open_in_docs_recreate_when_missing(
    mock_to_markdown, mock_get, mock_post, settings
):
    """A new docs document should be created when the old one is missing."""
    settings.DOCS_BASE_URL = "https://docs.example.com/"

    user = factories.UserFactory()
    ai_job = factories.AiFileJobFactory(
        file__creator=user,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.SUCCESS,
        docs_app_id="missing-doc-id",
        file__title="Weekly notes",
    )

    get_response = Mock()
    get_response.status_code = 404
    mock_get.return_value = get_response

    mock_to_markdown.return_value = "# Resume"
    post_response = Mock()
    post_response.raise_for_status.return_value = None
    post_response.json.return_value = {"id": "recreated-doc-id"}
    mock_post.return_value = post_response

    client = APIClient()
    client.force_login(user)
    _set_oidc_session(client, access_token="token-abc")

    response = client.post(f"/api/v1.0/ai-jobs/{ai_job.id}/open-in-docs/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "doc_url": "https://docs.example.com/docs/recreated-doc-id/"
    }

    mock_get.assert_called_once_with(
        "https://docs.example.com/external_api/v1.0/documents/missing-doc-id/",
        headers={"Authorization": "Bearer token-abc"},
        timeout=10,
    )
    mock_post.assert_called_once()

    ai_job.refresh_from_db()
    assert ai_job.docs_app_id == "recreated-doc-id"
