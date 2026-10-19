"""Rate limiting for expensive API operations."""

from functools import partial
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

import pytest
from rest_framework.test import APIClient

from core import factories, models
from core.api import throttling
from core.storage import get_storage_for_file

pytestmark = pytest.mark.django_db


def _retry(client, user):
    job = factories.AiFileJobFactory(
        file__creator=user,
        type=models.AiJobTypeChoices.TRANSCRIPT,
        status=models.AiJobStatusChoices.FAILED,
        file__upload_bytes=b"audio",
        file__audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    return client.post(f"/api/v1.0/ai-jobs/{job.id}/retry/", {"language": "en"})


def _create_in_docs(client, user):
    job = factories.AiFileJobFactory(
        file__creator=user,
        type=models.AiJobTypeChoices.TRANSCRIPT,
        status=models.AiJobStatusChoices.SUCCESS,
        docs_app_id=None,
    )
    return client.post(f"/api/v1.0/ai-jobs/{job.id}/create-in-docs/")


def _upload_ended(client, user):
    file = factories.FileFactory(creator=user, filename="recording.ogg")
    get_storage_for_file(file).save(file.temporary_file_key, BytesIO(b"audio"))
    return client.post(f"/api/v1.0/files/{file.id}/upload-ended/")


def _result(client, user, action):
    job = factories.AiFileJobFactory(
        file__creator=user,
        type=(
            models.AiJobTypeChoices.TRANSCRIPT
            if action == "transcript"
            else models.AiJobTypeChoices.SUMMARIZE
        ),
        status=models.AiJobStatusChoices.SUCCESS,
    )
    get_storage_for_file(job.file).save(job.key, BytesIO(b"{}"))
    return client.get(f"/api/v1.0/ai-jobs/{job.id}/{action}/")


ENDPOINTS = [
    ("ai_job_retry", _retry, 201),
    ("ai_job_create_in_docs", _create_in_docs, 201),
    ("file_upload_ended", _upload_ended, 200),
    ("ai_job_result", partial(_result, action="transcript"), 200),
    ("ai_job_result", partial(_result, action="summary"), 200),
]


@pytest.fixture(name="services", autouse=True)
def fixture_services(settings):
    """Keep external submissions mocked while exercising the real API actions."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False

    def create_document(job_id):
        models.AiFileJob.objects.filter(pk=job_id).update(docs_app_id=f"doc-{job_id}")

    with (
        mock.patch(
            "core.api.viewsets.call_transcribe_service",
            side_effect=lambda job_id: job_id,
        ) as retry,
        mock.patch(
            "core.api.viewsets.create_document_in_docs", side_effect=create_document
        ) as create_in_docs,
        mock.patch("core.api.viewsets.start_audio_extraction") as upload_ended,
    ):
        yield [retry, create_in_docs, upload_ended]


@pytest.fixture(name="rates")
def fixture_rates(settings, monkeypatch):
    """Restore every nested setting override after the test."""
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for scope in {endpoint[0] for endpoint in ENDPOINTS}:
        monkeypatch.setitem(rates, f"{scope}_burst", "2/minute")
        monkeypatch.setitem(rates, f"{scope}_sustained", "100/hour")
    return rates


@pytest.fixture(
    name="endpoint",
    params=ENDPOINTS,
    ids=["retry", "create_in_docs", "upload_ended", "transcript", "summary"],
)
def fixture_endpoint(request):
    """Send requests against fresh resources so allowances must span resources."""
    scope, handler, expected_status = request.param
    client = APIClient()
    user = factories.UserFactory()
    client.force_login(user)
    return SimpleNamespace(
        scope=scope,
        send=partial(handler, client),
        status=expected_status,
        client=client,
        user=user,
    )


@pytest.mark.parametrize(
    "throttle_class,requests,duration",
    [
        (throttling.AiJobRetryThrottleBurst, 3, 60),
        (throttling.AiJobRetryThrottleSustained, 20, 3600),
        (throttling.AiJobCreateInDocsThrottleBurst, 5, 60),
        (throttling.AiJobCreateInDocsThrottleSustained, 30, 3600),
        (throttling.FileUploadEndedThrottleBurst, 10, 60),
        (throttling.FileUploadEndedThrottleSustained, 100, 3600),
        (throttling.AiJobResultThrottleBurst, 60, 60),
        (throttling.AiJobResultThrottleSustained, 500, 3600),
    ],
)
def test_expensive_endpoint_default_rates(throttle_class, requests, duration):
    """Each operation has the agreed burst and sustained defaults."""
    throttle = throttle_class()
    assert (throttle.num_requests, throttle.duration) == (requests, duration)


@pytest.mark.parametrize("window,duration", [("burst", 60), ("sustained", 3600)])
def test_expensive_endpoint_limits_and_expiry(
    endpoint, rates, services, window, duration
):
    """Both windows block excess requests before side effects and expire on time."""
    rates[f"{endpoint.scope}_burst"] = "100/minute"
    rates[f"{endpoint.scope}_{window}"] = (
        f"2/{'minute' if window == 'burst' else 'hour'}"
    )
    with mock.patch("rest_framework.throttling.SimpleRateThrottle.timer") as timer:
        timer.return_value = 10000
        for _ in range(2):
            response = endpoint.send(endpoint.user)
            assert response.status_code == endpoint.status, response.content

        calls_before = [service.call_count for service in services]
        response = endpoint.send(endpoint.user)
        assert response.status_code == 429
        assert int(response["Retry-After"]) == duration
        assert [service.call_count for service in services] == calls_before

        timer.return_value += duration
        response = endpoint.send(endpoint.user)
        assert response.status_code == endpoint.status, response.content


@pytest.mark.usefixtures("rates")
def test_expensive_endpoint_allowance_is_per_user(endpoint):
    """One user exhausting their allowance does not affect another on the same IP."""
    for _ in range(2):
        assert endpoint.send(endpoint.user).status_code == endpoint.status
    assert endpoint.send(endpoint.user).status_code == 429

    other_user = factories.UserFactory()
    endpoint.client.force_login(other_user)
    assert endpoint.send(other_user).status_code == endpoint.status


@pytest.mark.usefixtures("rates")
def test_expensive_endpoint_allowances_are_independent():
    """Exhausting one operation leaves the other operations and reads available."""
    client = APIClient()
    user = factories.UserFactory()
    client.force_login(user)
    for _, handler, expected_status in ENDPOINTS[:4]:
        for _ in range(2):
            assert handler(client, user).status_code == expected_status
        assert handler(client, user).status_code == 429

    job = factories.AiFileJobFactory(
        file__creator=user,
        status=models.AiJobStatusChoices.SUCCESS,
        docs_app_id="existing-document",
    )
    for _ in range(3):
        assert client.get("/api/v1.0/files/").status_code == 200
        assert client.get(f"/api/v1.0/ai-jobs/{job.id}/").status_code == 200
        assert (
            client.post(f"/api/v1.0/ai-jobs/{job.id}/open-in-docs/").status_code == 200
        )


@pytest.mark.parametrize("window", ["burst", "sustained"])
def test_result_downloads_share_allowance(rates, window):
    """Alternating transcripts and summaries cannot multiply either allowance."""
    rates["ai_job_result_burst"] = "100/minute"
    rates[f"ai_job_result_{window}"] = f"2/{'minute' if window == 'burst' else 'hour'}"
    client = APIClient()
    user = factories.UserFactory()
    client.force_login(user)
    assert _result(client, user, "transcript").status_code == 200
    assert _result(client, user, "summary").status_code == 200
    assert _result(client, user, "transcript").status_code == 429
    assert _result(client, user, "summary").status_code == 429
