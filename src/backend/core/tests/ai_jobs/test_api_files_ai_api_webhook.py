"""
Tests for files API endpoint in dictaphone's core app: create
"""

import logging
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices

pytestmark = pytest.mark.django_db


def test_api_files_transcribe_webhook_anonymous(caplog):
    """Anonymous users should not be allowed to call webhook."""
    with caplog.at_level(logging.WARNING):
        response = APIClient().post(
            "/api/v1.0/ai-jobs/webhook/",
            {},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    assert "Bad Authorization header (ip:" in caplog.text


def test_api_files_transcribe_webhook_bad_token(caplog):
    """Anonymous users should not be allowed to call webhook."""
    with caplog.at_level(logging.WARNING):
        response = APIClient().post(
            "/api/v1.0/ai-jobs/webhook/",
            {},
            headers={"Authorization": "Bearer bad-key"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    assert "Bad Authorization header (ip:" in caplog.text


@patch("core.api.viewsets.handle_transcript_received")
def test_api_files_transcribe_webhook_authenticated(mock_task, settings):
    """Calls to the webhook with a proper API key should be accepted"""

    ai_file_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT, status=AiJobStatusChoices.PENDING
    )
    settings.AI_WEBHOOK_API_KEY = "good-key"
    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "job_id": ai_file_job.remote_job_id,
            "type": "transcript",
            "status": "success",
            "transcription_data_url": "http://example.com/transcription.json",
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Event processed."}

    assert mock_task.apply_async.called
    assert mock_task.apply_async.call_args[1]["args"] == [
        ai_file_job.remote_job_id,
        "http://example.com/transcription.json",
    ]


def test_api_files_transcribe_webhook_authenticated_already_success(settings):
    """Calls for an AI job that is already successful shouldn't do anything"""

    ai_file_job = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)
    ai_file_job.status = AiJobStatusChoices.SUCCESS
    ai_file_job.save()

    settings.AI_WEBHOOK_API_KEY = "good-key"
    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "job_id": ai_file_job.remote_job_id,
            "type": "transcript",
            "status": "success",
            "transcription_data_url": "http://example.com/transcription.json",
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "message": "AI file job already in success state, ignoring."
    }


@patch("core.api.viewsets.handle_transcript_received")
def test_api_files_transcribe_webhook_invalid_payload(mock_task, settings):
    """Invalid payloads should be rejected with a 400."""
    settings.AI_WEBHOOK_API_KEY = "good-key"

    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            # Missing required `job_id`
            "type": "transcript",
            "status": "success",
            "transcription_data_url": "http://example.com/transcription.json",
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert mock_task.apply_async.call_count == 0


@patch("core.api.viewsets.handle_transcript_received")
def test_api_files_transcribe_webhook_unknown_job_id(mock_task, settings):
    """Unknown jobs should be ignored without dispatching tasks."""
    settings.AI_WEBHOOK_API_KEY = "good-key"

    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "job_id": "missing-job-id",
            "type": "transcript",
            "status": "success",
            "transcription_data_url": "http://example.com/transcription.json",
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "No AI file job found for job ID, ignoring."}
    assert mock_task.apply_async.call_count == 0


@patch("core.api.viewsets.store_summary")
@patch("core.api.viewsets.handle_transcript_received")
def test_api_files_summary_webhook_success(
    mock_store_transcript, mock_store_summary, settings
):
    """Summary success events should enqueue summary storage task."""
    ai_file_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    )
    settings.AI_WEBHOOK_API_KEY = "good-key"

    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "job_id": ai_file_job.remote_job_id,
            "type": "summary",
            "status": "success",
            "summary_data_url": "http://example.com/summary.txt",
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Event processed."}
    assert mock_store_transcript.apply_async.call_count == 0
    mock_store_summary.apply_async.assert_called_once_with(
        args=[ai_file_job.remote_job_id, "http://example.com/summary.txt"]
    )


@pytest.mark.parametrize("payload_type", ["transcript", "summary"])
def test_api_files_webhook_failure_marks_job_failed(payload_type, settings):
    """Failure webhook events should mark the related job as FAILED."""
    ai_file_job = factories.AiFileJobFactory(status=AiJobStatusChoices.PENDING)
    settings.AI_WEBHOOK_API_KEY = "good-key"

    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "job_id": ai_file_job.remote_job_id,
            "type": payload_type,
            "status": "failure",
            "error_code": "unknown_error",
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Event processed."}

    ai_file_job.refresh_from_db()
    assert ai_file_job.status == AiJobStatusChoices.FAILED
