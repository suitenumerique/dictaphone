"""Tests for background tasks."""

from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.files.storage import default_storage

import pytest

from core import factories
from core.models import AiFileJob, AiJobStatusChoices, AiJobTypeChoices, File
from core.tasks.file import (
    call_transcribe_service,
    create_document_in_docs,
    handle_transcript_received,
    process_file_deletion,
    store_summary,
)

pytestmark = pytest.mark.django_db


def test_task_process_file_deletion_file_does_not_exist():
    """No error should be raised when trying to delete a missing file."""
    process_file_deletion(uuid4())


def test_task_process_file_deletion_file_not_hard_deleted():
    """A file that is not hard deleted must not be deleted."""
    file = factories.FileFactory(upload_bytes=b"hello")

    process_file_deletion(file.id)

    assert File.objects.filter(id=file.id).exists()
    assert default_storage.exists(file.file_key)


def test_task_process_file_deletion_success():
    """A hard-deleted file should be removed from storage and database."""
    file = factories.FileFactory(upload_bytes=b"hello")
    file.soft_delete()
    file.hard_delete()

    assert default_storage.exists(file.file_key)
    process_file_deletion(file.id)

    assert not File.objects.filter(id=file.id).exists()
    assert not default_storage.exists(file.file_key)


@patch("core.tasks.file.requests.post")
def test_task_call_transcribe_service_file_does_not_exist(mock_post):
    """External API should not be called when the file does not exist."""
    call_transcribe_service(uuid4())

    assert mock_post.call_count == 0


@patch("core.tasks.file.requests.post")
def test_task_call_transcribe_service_success(mock_post, settings):
    """Transcribe task should call AI service and create a pending transcript job."""
    settings.AI_SERVICE_URL = "http://ai-service/"
    settings.AI_SERVICE_API_KEY = "test-ai-key"
    file = factories.FileFactory(upload_bytes=b"hello")

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"job_id": "remote-transcript-job-id"}
    mock_post.return_value = response

    call_transcribe_service(file.id)

    assert mock_post.call_count == 1
    _, kwargs = mock_post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer test-ai-key"}
    assert kwargs["timeout"] == 10
    assert kwargs["json"]["user_sub"] == file.creator.sub
    assert kwargs["json"]["language"] == "fr"
    assert kwargs["json"]["cloud_storage_url"]

    ai_job = AiFileJob.objects.get(remote_job_id="remote-transcript-job-id")
    assert ai_job.file == file
    assert ai_job.type == AiJobTypeChoices.TRANSCRIPT
    assert ai_job.status == AiJobStatusChoices.PENDING


@patch("core.tasks.file.requests.post")
def test_task_call_transcribe_service_http_error(mock_post):
    """Errors from AI transcribe API should bubble up and mark job as failed."""
    file = factories.FileFactory(upload_bytes=b"hello")

    response = Mock()
    response.raise_for_status.side_effect = RuntimeError("transcribe failure")
    mock_post.return_value = response

    with pytest.raises(RuntimeError, match="transcribe failure"):
        call_transcribe_service(file.id)

    ai_job = AiFileJob.objects.get(file=file, type=AiJobTypeChoices.TRANSCRIPT)
    assert ai_job.status == AiJobStatusChoices.FAILED
    assert ai_job.remote_job_id is None


@patch("core.tasks.file.requests.post")
@patch("core.tasks.file.requests.get")
def test_task_store_transcript_and_call_summary_job_does_not_exist(mock_get, mock_post):
    """No external calls should be made for unknown remote job id."""
    handle_transcript_received(
        remote_job_id="missing-remote-job",
        url="http://example.com/transcript.json",
    )

    assert mock_get.call_count == 0
    assert mock_post.call_count == 0


@patch("core.tasks.file.requests.post")
@patch("core.tasks.file.requests.get")
def test_task_store_transcript_and_call_summary_ignores_non_transcript_job(
    mock_get, mock_post
):
    """No external calls should be made if remote id belongs to a non-transcript job."""
    ai_summary_job = factories.AiFileJobFactory(type=AiJobTypeChoices.SUMMARIZE)

    handle_transcript_received(
        remote_job_id=ai_summary_job.remote_job_id,
        url="http://example.com/transcript.json",
    )

    mock_get.assert_not_called()
    mock_post.assert_not_called()


@patch("core.tasks.file.create_document_in_docs.apply_async")
@patch("core.tasks.file.requests.post")
@patch("core.tasks.file.requests.get")
def test_task_store_transcript_and_call_summary_success(
    mock_get, mock_post, mock_create_document_in_docs, settings
):
    """Transcript should be stored, transcript job marked success and summary job created."""
    settings.AI_SERVICE_URL = "http://ai-service/"
    settings.AI_SERVICE_API_KEY = "test-ai-key"
    ai_transcript_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )

    transcript_payload = {
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "Bonjour",
                "words": [
                    {
                        "word": "Bonjour",
                        "start": 0.0,
                        "end": 1.0,
                        "score": 0.99,
                        "speaker": "SPEAKER_00",
                    }
                ],
                "speaker": "SPEAKER_00",
            }
        ],
        "word_segments": [
            {
                "word": "Bonjour",
                "start": 0.0,
                "end": 1.0,
                "score": 0.99,
                "speaker": "SPEAKER_00",
            }
        ],
    }
    transcript_content = b'{"transcript":"raw"}'

    get_response = Mock()
    get_response.raise_for_status.return_value = None
    get_response.json.return_value = transcript_payload
    get_response.content = transcript_content
    mock_get.return_value = get_response

    post_response = Mock()
    post_response.raise_for_status.return_value = None
    post_response.json.return_value = {"job_id": "remote-summary-job-id"}
    mock_post.return_value = post_response

    handle_transcript_received(
        remote_job_id=ai_transcript_job.remote_job_id,
        url="http://example.com/transcript.json",
    )

    mock_get.assert_called_once_with(
        "http://example.com/transcript.json",
        timeout=(10, 20),
    )
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer test-ai-key"}
    assert kwargs["timeout"] == 10
    assert kwargs["json"] == {
        "user_sub": ai_transcript_job.file.creator.sub,
        "language": "fr",
        "content": "\n\n**SPEAKER_00**: Bonjour",
    }
    mock_create_document_in_docs.assert_called_once_with(args=[ai_transcript_job.id])

    s3_client = default_storage.connection.meta.client
    stored_obj = s3_client.get_object(
        Bucket=default_storage.bucket_name,
        Key=ai_transcript_job.key,
    )
    assert stored_obj["Body"].read() == transcript_content

    ai_transcript_job.refresh_from_db()
    assert ai_transcript_job.status == AiJobStatusChoices.SUCCESS
    assert AiFileJob.objects.filter(
        remote_job_id="remote-summary-job-id",
        file=ai_transcript_job.file,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    ).exists()


@patch("core.tasks.file.requests.post")
@patch("core.tasks.file.requests.get")
def test_task_store_transcript_and_call_summary_get_error(mock_get, mock_post):
    """If transcript download fails, nothing should be persisted."""
    ai_transcript_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )

    get_response = Mock()
    get_response.raise_for_status.side_effect = RuntimeError("download failure")
    mock_get.return_value = get_response

    with pytest.raises(RuntimeError, match="download failure"):
        handle_transcript_received(
            remote_job_id=ai_transcript_job.remote_job_id,
            url="http://example.com/transcript.json",
        )

    ai_transcript_job.refresh_from_db()
    assert ai_transcript_job.status == AiJobStatusChoices.PENDING
    assert not AiFileJob.objects.filter(
        file=ai_transcript_job.file,
        type=AiJobTypeChoices.SUMMARIZE,
    ).exists()
    assert not default_storage.exists(f"transcripts/{ai_transcript_job.id!s}.json")
    assert mock_post.call_count == 0


@patch("core.tasks.file.requests.get")
def test_task_store_summary_job_does_not_exist(mock_get):
    """No external calls should be made for unknown summary remote job id."""
    store_summary(
        remote_job_id="missing-summary-job",
        url="http://example.com/summary.txt",
    )

    mock_get.assert_not_called()


@patch("core.tasks.file.requests.get")
def test_task_store_summary_ignores_non_summary_job(mock_get):
    """No external calls should be made if remote id belongs to a non-summary job."""
    ai_transcript_job = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)

    store_summary(
        remote_job_id=ai_transcript_job.remote_job_id,
        url="http://example.com/summary.txt",
    )

    mock_get.assert_not_called()


@patch("core.tasks.file.requests.get")
def test_task_store_summary_success(mock_get):
    """Summary should be stored and summary job marked success."""
    ai_summary_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    )

    summary_content = b"Summary content"
    get_response = Mock()
    get_response.raise_for_status.return_value = None
    get_response.content = summary_content
    mock_get.return_value = get_response

    store_summary(
        remote_job_id=ai_summary_job.remote_job_id,
        url="http://example.com/summary.txt",
    )

    mock_get.assert_called_once_with(
        "http://example.com/summary.txt",
        timeout=(10, 20),
    )

    s3_client = default_storage.connection.meta.client
    stored_obj = s3_client.get_object(
        Bucket=default_storage.bucket_name,
        Key=ai_summary_job.key,
    )
    assert stored_obj["Body"].read() == summary_content

    ai_summary_job.refresh_from_db()
    assert ai_summary_job.status == AiJobStatusChoices.SUCCESS


@patch("core.tasks.file.requests.get")
def test_task_store_summary_get_error(mock_get):
    """If summary download fails, nothing should be persisted."""
    ai_summary_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    )
    get_response = Mock()
    get_response.raise_for_status.side_effect = RuntimeError("download failure")
    mock_get.return_value = get_response

    with pytest.raises(RuntimeError, match="download failure"):
        store_summary(
            remote_job_id=ai_summary_job.remote_job_id,
            url="http://example.com/summary.txt",
        )

    ai_summary_job.refresh_from_db()
    assert ai_summary_job.status == AiJobStatusChoices.PENDING
    assert not default_storage.exists(f"summaries/{ai_summary_job.id!s}.txt")


@patch("core.tasks.file.create_document_in_docs.apply_async")
@patch("core.tasks.file.requests.post")
@patch("core.tasks.file.requests.get")
def test_task_store_transcript_and_call_summary_post_error(
    mock_get, mock_post, mock_create_document_in_docs
):
    """
    If summary API fails after transcript storage, transcript remains saved and
    transcript job stays SUCCESS and summary job is created as failed.
    """
    ai_transcript_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )

    get_response = Mock()
    get_response.raise_for_status.return_value = None
    get_response.content = b'{"transcript":"raw"}'
    get_response.json.return_value = {
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "Bonjour",
                "words": [],
                "speaker": "SPEAKER_00",
            }
        ],
        "word_segments": [],
    }
    mock_get.return_value = get_response

    post_response = Mock()
    post_response.raise_for_status.side_effect = RuntimeError("summary failure")
    mock_post.return_value = post_response

    with pytest.raises(RuntimeError, match="summary failure"):
        handle_transcript_received(
            remote_job_id=ai_transcript_job.remote_job_id,
            url="http://example.com/transcript.json",
        )

    ai_transcript_job.refresh_from_db()
    assert ai_transcript_job.status == AiJobStatusChoices.SUCCESS
    assert default_storage.exists(f"transcripts/{ai_transcript_job.id!s}.json")
    ai_summary_job = AiFileJob.objects.get(
        file=ai_transcript_job.file,
        type=AiJobTypeChoices.SUMMARIZE,
    )
    assert ai_summary_job.status == AiJobStatusChoices.FAILED
    assert ai_summary_job.remote_job_id is None
    mock_create_document_in_docs.assert_called_once_with(args=[ai_transcript_job.id])


@patch("core.tasks.file.requests.post")
def test_task_create_document_in_docs_ignores_non_transcript_job(mock_post):
    """Non-transcript jobs should not trigger Docs document creation."""
    ai_summary_job = factories.AiFileJobFactory(type=AiJobTypeChoices.SUMMARIZE)

    create_document_in_docs(ai_summary_job.id)

    mock_post.assert_not_called()


@patch("core.tasks.file.requests.post")
def test_task_create_document_in_docs_ignores_existing_doc(mock_post):
    """Jobs with existing docs id should not call Docs API again."""
    ai_transcript_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        docs_app_id="existing-doc-id",
    )

    create_document_in_docs(ai_transcript_job.id)

    mock_post.assert_not_called()


@patch("core.tasks.file.requests.post")
@patch("core.tasks.file.AiFileJob.to_markdown")
def test_task_create_document_in_docs_success(mock_to_markdown, mock_post, settings):
    """Transcript jobs should create Docs documents and store docs id."""
    settings.DOCS_BASE_URL = "https://docs.example.com"
    settings.DOCS_SERVER_TO_SERVER_API_KEY = "docs-api-key"
    ai_transcript_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        docs_app_id=None,
        file__title="Meeting notes",
    )

    mock_to_markdown.return_value = "# Transcript"
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"id": "new-doc-id"}
    mock_post.return_value = response

    create_document_in_docs(ai_transcript_job.id)

    mock_post.assert_called_once_with(
        "https://docs.example.com/api/v1.0/documents/create-for-owner/",
        json={
            "title": "Meeting notes",
            "content": "# Transcript",
            "email": ai_transcript_job.file.creator.email,
            "sub": ai_transcript_job.file.creator.sub,
        },
        headers={"Authorization": "Bearer docs-api-key"},
        timeout=20,
    )
    ai_transcript_job.refresh_from_db()
    assert ai_transcript_job.docs_app_id == "new-doc-id"


@patch("core.tasks.file.logger.error")
@patch("core.tasks.file.requests.post")
@patch("core.tasks.file.AiFileJob.to_markdown")
def test_task_create_document_in_docs_logs_and_raises_on_http_error(
    mock_to_markdown, mock_post, mock_logger_error, settings
):
    """Non-201 Docs responses should be logged and raised."""
    settings.DOCS_BASE_URL = "https://docs.example.com"
    settings.DOCS_SERVER_TO_SERVER_API_KEY = "docs-api-key"
    ai_transcript_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        docs_app_id=None,
    )

    mock_to_markdown.return_value = "# Transcript"
    response = Mock()
    response.status_code = 500
    response.text = "docs failure body"
    response.raise_for_status.side_effect = RuntimeError("docs failure")
    mock_post.return_value = response

    with pytest.raises(RuntimeError, match="docs failure"):
        create_document_in_docs(ai_transcript_job.id)

    mock_logger_error.assert_called_once_with(
        "Failed to create document in Docs for file %s: %s",
        ai_transcript_job.file.id,
        "docs failure body",
    )
    response.raise_for_status.assert_called_once_with()
    ai_transcript_job.refresh_from_db()
    assert ai_transcript_job.docs_app_id is None
