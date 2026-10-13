"""Regression tests for transcription reservation and submission retries."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

from django.core.files.storage import default_storage
from django.db import connections

import pytest
import requests

from core import factories
from core.models import (
    AiJobStatusChoices,
    AiJobTypeChoices,
    FileAudioExtractionStateChoices,
)
from core.tasks.file import (
    PermanentTranscriptionError,
    TranscriptionAlreadyPending,
    call_transcribe_service,
    create_transcription_job,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "state",
    [
        FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION,
        FileAudioExtractionStateChoices.AUDIO_EXTRACTION_FAILED,
    ],
)
def test_create_transcription_job_requires_validated_audio(state):
    """Invalid input cannot leave a pending job waiting for submission."""
    file = factories.FileFactory(audio_extraction_state=state)

    with pytest.raises(ValueError, match="successfully validated audio"):
        create_transcription_job(file.id)

    assert not file.ai_jobs.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_transcript_retries_reserve_one_pending_job():
    """The pending check and job creation serialize on the owning file."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    barrier = Barrier(2)

    def reserve(_):
        try:
            barrier.wait(timeout=10)
            return create_transcription_job(file.pk, allow_pending=False).pk
        except TranscriptionAlreadyPending:
            return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, range(2)))

    assert results.count(None) == 1
    assert file.ai_jobs.count() == 1
    assert file.ai_jobs.get().pk in results


@patch("core.tasks.file.session.post")
def test_transcription_missing_reserved_audio_marks_job_failed(mock_post):
    """Input removed after reservation produces a terminal failure."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = create_transcription_job(file.pk)
    default_storage.delete(job.validated_audio_job.source_job.output_key)

    with pytest.raises(ValueError, match="successfully validated audio"):
        call_transcribe_service(job.pk)

    mock_post.assert_not_called()
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.FAILED


@patch("core.tasks.file.session.post")
@pytest.mark.parametrize("payload", [{}, {"job_id": None}, {"job_id": ""}])
def test_transcription_invalid_service_response_marks_job_failed(mock_post, payload):
    """An unusable remote job ID cannot leave the local job pending indefinitely."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = create_transcription_job(file.pk)
    response = Mock()
    response.json.return_value = payload
    mock_post.return_value = response

    result = call_transcribe_service.apply(args=[job.pk], throw=False)

    assert result.failed()
    mock_post.assert_called_once()
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.FAILED
    assert job.remote_job_id is None


@patch("core.tasks.file.session.post")
def test_transcription_retry_preserves_job_and_pending_status(mock_post):
    """A transient failure retries the same pending record and input."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
        language="fr",
    )
    job = create_transcription_job(file.pk, language="en")
    file.language = "de"
    file.save(update_fields=["language"])
    attempts = []

    def submit(*args, **kwargs):
        job.refresh_from_db()
        attempts.append(kwargs["json"])
        assert job.status == AiJobStatusChoices.PENDING
        assert file.ai_jobs.count() == 1
        if len(attempts) == 1:
            raise requests.ConnectionError("temporary failure")
        response = Mock()
        response.json.return_value = {"job_id": "retried-transcript"}
        return response

    mock_post.side_effect = submit

    result = call_transcribe_service.apply(args=[job.pk], throw=False)

    assert result.successful(), result.result
    assert result.result == job.pk
    assert mock_post.call_count == 2
    assert all(attempt["language"] == "en" for attempt in attempts)
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.PENDING
    assert job.remote_job_id == "retried-transcript"


@patch("core.tasks.file.session.post")
def test_transcription_retry_exhaustion_marks_one_job_failed(mock_post):
    """Only the final exhausted attempt makes a transient failure terminal."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = create_transcription_job(file.pk)
    statuses = []

    def submit(*args, **kwargs):
        job.refresh_from_db()
        statuses.append(job.status)
        raise requests.Timeout("service unavailable")

    mock_post.side_effect = submit
    expected_attempts = call_transcribe_service.retry_kwargs["max_retries"] + 1
    result = call_transcribe_service.apply(args=[job.pk], throw=False)

    assert result.failed()
    assert statuses == [AiJobStatusChoices.PENDING] * expected_attempts
    assert file.ai_jobs.count() == 1
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.FAILED
    assert job.remote_job_id is None
    call_transcribe_service(job.pk)
    assert mock_post.call_count == expected_attempts


@patch("core.tasks.file.session.post")
@pytest.mark.parametrize("status_code", [400, 401, 403, 422])
def test_transcription_permanent_http_error_is_not_retried(mock_post, status_code):
    """Client errors fail immediately, without exhausting network retries."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = create_transcription_job(file.pk)
    response = requests.Response()
    response.status_code = status_code
    mock_post.return_value = response

    result = call_transcribe_service.apply(args=[job.pk], throw=False)

    assert result.failed()
    assert isinstance(result.result, PermanentTranscriptionError)
    mock_post.assert_called_once()
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.FAILED


@patch("core.tasks.file.session.post")
@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
def test_transcription_retryable_http_error_can_recover(mock_post, status_code):
    """Timeouts, throttling and server errors can recover using the same job."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = create_transcription_job(file.pk)
    failure = requests.Response()
    failure.status_code = status_code
    success = Mock()
    success.json.return_value = {"job_id": "recovered-transcript"}
    mock_post.side_effect = [failure, success]

    result = call_transcribe_service.apply(args=[job.pk], throw=False)

    assert result.successful(), result.result
    assert mock_post.call_count == 2
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.PENDING
    assert job.remote_job_id == "recovered-transcript"


@patch("core.tasks.file.session.post")
def test_transcription_already_submitted_is_not_submitted_again(mock_post):
    """Repeated task delivery does not create another remote job."""
    job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
        remote_job_id="already-submitted",
    )

    assert call_transcribe_service(job.pk) == job.pk

    mock_post.assert_not_called()


@pytest.mark.django_db(transaction=True)
@patch("core.tasks.file.session.post")
def test_concurrent_transcription_submissions_call_service_once(mock_post):
    """Concurrent workers serialize submission of a single reserved job."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = create_transcription_job(file.pk)
    response = Mock()
    response.json.return_value = {"job_id": "one-remote-transcript"}
    mock_post.return_value = response
    barrier = Barrier(2)

    def submit(_):
        try:
            barrier.wait(timeout=10)
            return call_transcribe_service(job.pk)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(submit, range(2))) == [job.pk, job.pk]

    mock_post.assert_called_once()
    job.refresh_from_db()
    assert job.remote_job_id == "one-remote-transcript"
    assert file.ai_jobs.count() == 1
