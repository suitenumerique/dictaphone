"""Regression coverage for bounded AI results and incoming webhook JSON."""

import gzip
from io import BytesIO
from unittest.mock import Mock, PropertyMock, patch

from django.core.files.storage import default_storage
from django.utils import timezone

import pytest
import requests
from rest_framework.exceptions import ParseError
from rest_framework.test import APIClient
from urllib3.response import HTTPResponse

from core import factories
from core.api.parsers import BoundedWebhookJSONParser, PayloadTooLarge
from core.models import AiFileJob, AiJobStatusChoices, FileAudioExtractionStateChoices
from core.payloads import (
    PayloadLimitExceeded,
    read_response,
    read_stored_result,
    result_limit,
)
from core.tasks.file import (
    call_transcribe_service,
    create_document_in_docs,
    create_transcription_job,
    handle_transcript_received,
    store_summary,
)


def response_for(content, headers=None):
    """Use actual Requests/urllib3 streaming, including decompression."""
    response = requests.Response()
    response.status_code = 200
    response.headers.update(headers or {})
    response.raw = HTTPResponse(
        body=BytesIO(content),
        headers={
            key: value
            for key, value in (headers or {}).items()
            if key.lower() != "content-length"
        },
        preload_content=False,
    )
    return response


@pytest.mark.parametrize("length", [None, "1", "invalid"])
def test_count_actual_bytes_despite_headers(length):
    """Missing, lying, or malformed metadata cannot bypass byte counting."""
    response = response_for(b"a" * 11, {"Content-Length": length} if length else {})
    with pytest.raises(PayloadLimitExceeded):
        read_response(response, 10)
    assert response.raw.closed


def test_large_content_length_rejected_before_read():
    """An advertised oversize avoids reading any response bytes."""
    response = Mock(headers={"Content-Length": "11"})
    with pytest.raises(PayloadLimitExceeded):
        read_response(response, 10)
    response.iter_content.assert_not_called()
    response.close.assert_called_once()


def test_count_decompressed_bytes():
    """A small compressed body still exceeds the decompressed byte ceiling."""
    compressed = gzip.compress(b"a" * 100_000)
    response = response_for(
        compressed,
        {"Content-Encoding": "gzip", "Content-Length": str(len(compressed))},
    )
    with pytest.raises(PayloadLimitExceeded):
        read_response(response, 1000)
    assert response.raw.closed


@pytest.mark.parametrize("content", [b"", b"legitimate", "résumé".encode()])
def test_accept_at_byte_limit(content):
    """Bounds include valid UTF-8 results exactly at the ceiling."""
    assert read_response(response_for(content), len(content)) == content


def test_limits_are_distinct(settings):
    """Transcripts and summaries keep independent configurable ceilings."""
    settings.PAYLOAD_TRANSCRIPT_MAX_BYTES = 42
    settings.PAYLOAD_SUMMARY_MAX_BYTES = 7
    assert result_limit("transcript") == 42
    assert result_limit("summary") == 7


@pytest.mark.parametrize("advertised", [None, "1", "invalid", "1000"])
def test_webhook_byte_limit(settings, advertised):
    """Check stream bytes independently of the incoming length header."""
    settings.PAYLOAD_WEBHOOK_MAX_BYTES = 10
    request = Mock(META={"CONTENT_LENGTH": advertised})
    with pytest.raises(PayloadTooLarge):
        BoundedWebhookJSONParser().parse(
            BytesIO(b'{"long": "body"}'), parser_context={"request": request}
        )


def test_webhook_legitimate_json():
    """Byte-bounded bodies use the standard DRF JSON parser."""
    assert BoundedWebhookJSONParser().parse(BytesIO(b'{"job_id": "job"}')) == {
        "job_id": "job"
    }


@pytest.mark.parametrize("content", [b'{"job_id":', b'{"job_id": NaN}'])
def test_webhook_invalid_json_is_a_parse_error(content):
    """Malformed JSON and nonstandard constants use DRF parse errors."""
    with pytest.raises(ParseError):
        BoundedWebhookJSONParser().parse(BytesIO(content))


@pytest.mark.parametrize("job_type", ["transcript", "summary"])
@pytest.mark.parametrize("oversized", [False, True])
def test_result_tasks_validate_before_writing(settings, job_type, oversized):
    """Reject without retry, storage write, or follow-up work; accept valid results."""
    settings.PAYLOAD_TRANSCRIPT_MAX_BYTES = 64
    settings.PAYLOAD_SUMMARY_MAX_BYTES = 64
    content = (
        b'{"segments": [], "word_segments": []}'
        if job_type == "transcript"
        else b"A legitimate summary"
    )
    if oversized:
        content = b"a" * 65
    response = response_for(content, {"Content-Length": "1"})
    job = Mock(type=job_type, created_at=timezone.now())
    task = handle_transcript_received if job_type == "transcript" else store_summary
    with (
        patch("core.tasks.file.AiFileJob.objects") as jobs,
        patch("core.tasks.file.fetch_external_source", return_value=response),
        patch("core.tasks.file.get_storage_for_file") as storage,
        patch("core.tasks.file.get_storage_bucket_name", return_value="bucket"),
        patch("core.tasks.file.analytics.capture_event"),
        patch("core.tasks.file.get_profile_for_email") as profile,
        patch.object(task, "retry") as retry,
    ):
        jobs.filter.return_value.first.return_value = job
        profile.return_value.auto_create_in_docs = False
        profile.return_value.send_notification_email = False
        if oversized:
            with pytest.raises(PayloadLimitExceeded):
                task.apply(args=["job", "https://example.com/result"], throw=True)
            job.mark_failed.assert_called_once()
            storage.assert_not_called()
        else:
            task.apply(args=["job", "https://example.com/result"], throw=True)
            storage.return_value.connection.meta.client.put_object.assert_called_once()
            kwargs = (
                storage.return_value.connection.meta.client.put_object.call_args.kwargs
            )
            assert kwargs["Body"] == content
            assert job.status == AiJobStatusChoices.SUCCESS
        retry.assert_not_called()
        jobs.create.assert_not_called()
    assert response.raw.closed


@pytest.mark.parametrize("job_type", ["transcript", "summary"])
@pytest.mark.parametrize("advertised", [None, 1, 1000])
def test_stored_results_bounded_without_spooling(settings, job_type, advertised):
    """Legacy oversized objects are bounded for exports and API downloads too."""
    settings.PAYLOAD_TRANSCRIPT_MAX_BYTES = 10
    settings.PAYLOAD_SUMMARY_MAX_BYTES = 10
    body = BytesIO(b"a" * 11)
    storage = Mock()
    storage.connection.meta.client.get_object.return_value = {
        "ContentLength": advertised,
        "Body": body,
    }
    with patch("core.payloads.get_storage_bucket_name", return_value="bucket"):
        with pytest.raises(PayloadLimitExceeded):
            read_stored_result(storage, "key", job_type)
    assert body.closed
    storage.open.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("job_type", ["transcript", "summary"])
def test_oversized_job_has_no_stored_result(settings, job_type):
    """Persist terminal failure with no object or summary job left behind."""

    settings.PAYLOAD_TRANSCRIPT_MAX_BYTES = 10
    settings.PAYLOAD_SUMMARY_MAX_BYTES = 10
    job = factories.AiFileJobFactory(type=job_type, status=AiJobStatusChoices.PENDING)
    task = handle_transcript_received if job_type == "transcript" else store_summary
    with (
        patch(
            "core.tasks.file.fetch_external_source",
            return_value=response_for(b"x" * 11),
        ),
        patch.object(task, "retry") as retry,
        pytest.raises(PayloadLimitExceeded),
    ):
        task.apply(args=[job.remote_job_id, "https://example.com/result"], throw=True)
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.FAILED
    assert not default_storage.exists(job.key)
    assert AiFileJob.objects.filter(file=job.file).count() == 1
    retry.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("request_format", ["json", "multipart"])
def test_webhook_rejects_oversized_without_dispatch(settings, request_format):
    """All supported webhook formats enforce limits before scheduling work."""
    settings.AI_WEBHOOK_API_KEY = "test-key"
    settings.PAYLOAD_WEBHOOK_MAX_BYTES = 10
    with patch("core.api.viewsets.handle_transcript_received.apply_async") as dispatch:
        response = APIClient().post(
            "/api/v1.0/ai-jobs/webhook/",
            {"job_id": "x" * 100},
            format=request_format,
            headers={"Authorization": "Bearer test-key"},
        )
    assert response.status_code == 413
    dispatch.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("job_type", ["transcript", "summary"])
def test_legacy_oversized_results_cannot_be_served_or_exported(settings, job_type):
    """Apply receive limits to older stored results at both consumer boundaries."""

    settings.PAYLOAD_TRANSCRIPT_MAX_BYTES = 10
    settings.PAYLOAD_SUMMARY_MAX_BYTES = 10
    job = factories.AiFileJobFactory(type=job_type, status=AiJobStatusChoices.SUCCESS)
    default_storage.save(job.key, BytesIO(b"x" * 11))
    with pytest.raises(PayloadLimitExceeded):
        job.to_markdown()
    client = APIClient()
    client.force_authenticate(job.file.creator)
    response = client.get(f"/api/v1.0/ai-jobs/{job.id}/{job_type}/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_docs_releases_claim_when_stored_transcript_is_oversized(settings):
    """Rejected legacy content must not leave an in-progress Docs claim."""
    settings.PAYLOAD_TRANSCRIPT_MAX_BYTES = 10
    job = factories.AiFileJobFactory(
        type="transcript", status=AiJobStatusChoices.SUCCESS
    )
    default_storage.save(job.key, BytesIO(b"x" * 11))
    with (
        patch("core.tasks.file.session.post") as post,
        pytest.raises(PayloadLimitExceeded),
    ):
        create_document_in_docs(job.id)
    job.refresh_from_db()
    assert not job.docs_creation_in_progress
    assert job.docs_app_id is None
    post.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "content",
    [
        b'{"segments":' + b"[" * 1000 + b"]" * 1000 + b"}",
        b'{"segments": [0, 0, 0, 0, 0, 0, 0], "word_segments": []}',
        b'{"segments": [], "word_segments": 42}',
        b'{"segments":',
    ],
)
def test_invalid_transcript_has_no_partial_result(content):
    """Parser and schema rejection is permanent and precedes S3 writes."""
    job = factories.AiFileJobFactory(
        type="transcript", status=AiJobStatusChoices.PENDING
    )
    with (
        patch(
            "core.tasks.file.fetch_external_source", return_value=response_for(content)
        ),
        patch.object(handle_transcript_received, "retry") as retry,
        pytest.raises(ValueError),
    ):
        handle_transcript_received.apply(
            args=[job.remote_job_id, "https://example.com/result"], throw=True
        )
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.FAILED
    assert not default_storage.exists(job.key)
    assert AiFileJob.objects.filter(file=job.file).count() == 1
    retry.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["transcribe", "summarize", "docs"])
@pytest.mark.parametrize("body_kind", ["valid", "oversized", "gzip", "invalid_json"])
def test_service_response_limits(settings, operation, body_kind):
    """Bound every acknowledgement before parsing and preserve terminal state."""
    settings.PAYLOAD_SERVICE_RESPONSE_MAX_BYTES = 64
    payload = b'{"job_id":"accepted-job","id":"accepted-doc"}'
    headers = {}
    if body_kind == "oversized":
        payload += b" " * 64
        headers["Content-Length"] = "1"
    elif body_kind == "gzip":
        payload = gzip.compress(payload + b" " * 1000)
        headers = {"Content-Length": str(len(payload)), "Content-Encoding": "gzip"}
    elif body_kind == "invalid_json":
        payload = b"{"
    response = response_for(payload, headers)
    response.status_code = 201
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    if operation == "transcribe":
        job = create_transcription_job(file.pk)
        task = call_transcribe_service
        args = [job.pk]
    else:
        job = factories.AiFileJobFactory(
            file=file,
            type="transcript",
            status=(
                AiJobStatusChoices.SUCCESS
                if operation == "docs"
                else AiJobStatusChoices.PENDING
            ),
        )
        task = (
            create_document_in_docs
            if operation == "docs"
            else handle_transcript_received
        )
        args = (
            [job.pk]
            if operation == "docs"
            else [job.remote_job_id, "https://example.com/result"]
        )
    transcript = b'{"segments":[{"text":"Hello","words":[]}],"word_segments":[]}'
    with (
        patch("core.tasks.file.session.post", return_value=response) as post,
        patch(
            "core.tasks.file.fetch_external_source",
            return_value=response_for(transcript),
        ),
        patch("core.tasks.file.AiFileJob.to_markdown", return_value="Transcript"),
        patch("core.tasks.file.get_profile_for_email") as profile,
        patch("core.tasks.file.analytics.capture_event"),
        patch.object(task, "retry") as retry,
        patch.object(
            requests.Response,
            "content",
            new_callable=PropertyMock,
            side_effect=AssertionError("Responses must be streamed"),
        ) as buffered_content,
    ):
        profile.return_value.auto_create_in_docs = False
        profile.return_value.send_notification_email = False
        if body_kind == "valid":
            task.apply(args=args, throw=True)
        else:
            with pytest.raises(ValueError):
                task.apply(args=args, throw=True)
        post.assert_called_once()
        assert post.call_args.kwargs["stream"] is True
        retry.assert_not_called()
    assert response.raw.closed
    buffered_content.assert_not_called()
    if operation == "summarize":
        job = AiFileJob.objects.get(file=file, type="summary")
    else:
        job.refresh_from_db()
    if operation == "docs":
        assert not job.docs_creation_in_progress
        assert job.docs_app_id == ("accepted-doc" if body_kind == "valid" else None)
    elif body_kind == "valid":
        assert job.remote_job_id == "accepted-job"
        assert job.status == AiJobStatusChoices.PENDING
    else:
        assert job.remote_job_id is None
        assert job.status == AiJobStatusChoices.FAILED


def test_http_failure_closes_response_without_reading_body():
    """Error responses need no body read to retain HTTP retry semantics."""
    response = Mock(status_code=500)
    response.raise_for_status.side_effect = requests.HTTPError("unavailable")
    with pytest.raises(requests.HTTPError):
        read_response(response, 64, check_status=True)
    response.iter_content.assert_not_called()
    response.close.assert_called_once()
