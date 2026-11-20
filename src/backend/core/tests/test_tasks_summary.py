"""Tests for summary job orchestration."""

from unittest.mock import patch

import pytest

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices
from core.tasks.file import handle_transcript_received

pytestmark = pytest.mark.django_db


@patch("core.tasks.file.send_transcription_ready_email.apply_async")
@patch("core.tasks.file.session.post")
@patch("core.tasks.file.session.get")
def test_task_store_transcript_with_summary_disabled(
    mock_get, mock_post, mock_send_email, settings
):
    """The transcript succeeds without creating a summary job when disabled."""
    settings.AI_SUMMARY_ENABLED = False
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = ["http://example.com/"]
    settings.EXTERNAL_SOURCE_REQUIRE_HTTPS = False
    settings.DATA_POLICY_CONFIGURATIONS = {
        "default": {
            "default": True,
            "auto_create_in_docs": False,
            "send_notification_email": True,
        }
    }
    transcript_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT, status=AiJobStatusChoices.PENDING
    )
    mock_get.return_value.headers = {}
    mock_get.return_value.iter_content.return_value = [
        b'{"segments": [{"start": 0, "end": 1, "text": "Bonjour", "words": []}],'
        b'"word_segments": []}'
    ]

    handle_transcript_received(
        transcript_job.remote_job_id, "http://example.com/result"
    )

    mock_post.assert_not_called()
    mock_send_email.assert_called_once_with(args=[transcript_job.id])
    transcript_job.refresh_from_db()
    assert transcript_job.status == AiJobStatusChoices.SUCCESS
    assert not transcript_job.file.ai_jobs.filter(
        type=AiJobTypeChoices.SUMMARIZE
    ).exists()
