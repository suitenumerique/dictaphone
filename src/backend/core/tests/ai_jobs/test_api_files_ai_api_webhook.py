"""
Tests for files API endpoint in dictaphone's core app: create
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from django.db import connections

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories, utils
from core.models import AiJobStatusChoices, AiJobTypeChoices

pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_api_files_webhook_serializes_same_job(settings):
    """A concurrent webhook must read the job state after its predecessor commits."""
    job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT, status=AiJobStatusChoices.PENDING
    )
    settings.AI_WEBHOOK_API_KEY = "good-key"
    dispatch_started = Event()
    second_lock_attempted = Event()
    acquire_lock = utils.acquire_transaction_lock

    def lock(key):
        if dispatch_started.is_set():
            second_lock_attempted.set()
        acquire_lock(key)

    def complete_job(**_kwargs):
        dispatch_started.set()
        assert second_lock_attempted.wait(timeout=10)
        job.status = AiJobStatusChoices.SUCCESS
        job.save()

    def send_webhook():
        try:
            return APIClient().post(
                "/api/v1.0/ai-jobs/webhook/",
                {
                    "job_id": job.remote_job_id,
                    "type": "transcript",
                    "status": "success",
                    "transcription_data_url": "http://example.com/transcription.json",
                },
                headers={"Authorization": "Bearer good-key"},
            )
        finally:
            connections.close_all()

    with (
        patch("core.api.viewsets.utils.acquire_transaction_lock", side_effect=lock),
        patch(
            "core.api.viewsets.handle_transcript_received.apply_async",
            side_effect=complete_job,
        ) as dispatch,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first = executor.submit(send_webhook)
        assert dispatch_started.wait(timeout=10)
        second = executor.submit(send_webhook)
        responses = [first.result(timeout=15), second.result(timeout=15)]

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == {"message": "Event processed."}
    assert responses[1].json() == {
        "message": "AI file job already in success state, ignoring."
    }
    dispatch.assert_called_once()


def test_api_files_webhook_rolls_back_failure(settings):
    """An error during webhook handling must roll back job and quota changes."""
    job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT, status=AiJobStatusChoices.PENDING
    )
    usage = factories.TranscriptionUsageFactory(ai_job_id=job.pk, user=job.file.creator)
    settings.AI_WEBHOOK_API_KEY = "good-key"

    with (
        patch(
            "core.api.viewsets.analytics.capture_event",
            side_effect=RuntimeError("Analytics failed"),
        ),
        pytest.raises(RuntimeError, match="Analytics failed"),
    ):
        APIClient().post(
            "/api/v1.0/ai-jobs/webhook/",
            {
                "job_id": job.remote_job_id,
                "type": "transcript",
                "status": "failure",
                "error_code": "unknown_error",
            },
            headers={"Authorization": "Bearer good-key"},
        )

    job.refresh_from_db()
    usage.refresh_from_db()
    assert job.status == AiJobStatusChoices.PENDING
    assert job.failure_reason == ""
    assert not usage.ignored


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


def test_api_files_transcribe_webhook_no_audio_in_file(settings):
    """An empty-audio failure should create an empty transcript."""
    ai_file_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )
    settings.AI_WEBHOOK_API_KEY = "good-key"

    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "job_id": ai_file_job.remote_job_id,
            "type": "transcript",
            "status": "failure",
            "error_code": "no_audio_in_file",
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Event processed."}

    ai_file_job.refresh_from_db()
    assert ai_file_job.status == AiJobStatusChoices.SUCCESS


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


@pytest.mark.parametrize(
    "payload_type,error_code,reason",
    [
        ("transcript", "unknown_error", "UNKNOWN_FAILURE"),
        ("summary", "unknown_error", "UNKNOWN_FAILURE"),
        ("transcript", "media_duration_too_long", "AUDIO_TOO_LONG"),
        ("transcript", "unexpected_service_error", "UNKNOWN_FAILURE"),
        ("summary", "unexpected_service_error", "UNKNOWN_FAILURE"),
    ],
)
def test_api_files_webhook_failure_marks_job_failed(
    payload_type, error_code, reason, settings
):
    """Failure webhook events should mark the related job as FAILED."""
    ai_file_job = factories.AiFileJobFactory(
        type=payload_type, status=AiJobStatusChoices.PENDING
    )
    transcript = (
        ai_file_job
        if payload_type == "transcript"
        else factories.AiFileJobFactory(
            file=ai_file_job.file, type="transcript", status=AiJobStatusChoices.SUCCESS
        )
    )
    usage = factories.TranscriptionUsageFactory(
        ai_job_id=transcript.pk, user=ai_file_job.file.creator
    )
    settings.AI_WEBHOOK_API_KEY = "good-key"

    response = APIClient().post(
        "/api/v1.0/ai-jobs/webhook/",
        {
            "job_id": ai_file_job.remote_job_id,
            "type": payload_type,
            "status": "failure",
            "error_code": error_code,
        },
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Event processed."}

    ai_file_job.refresh_from_db()
    assert ai_file_job.status == AiJobStatusChoices.FAILED
    assert ai_file_job.failure_reason == reason
    usage.refresh_from_db()
    assert usage.ignored == (payload_type == "transcript")
    assert usage.ignored_reason == (
        f"Transcription failed: {reason}" if payload_type == "transcript" else ""
    )
