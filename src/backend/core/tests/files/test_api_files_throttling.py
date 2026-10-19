"""Tests for per-user file creation rate limits."""

from unittest import mock

import pytest
from rest_framework.test import APIClient

from core import factories, models
from core.api.throttling import FileCreateThrottleBurst, FileCreateThrottleSustained

pytestmark = pytest.mark.django_db

URL = "/api/v1.0/files/"
PAYLOAD = {
    "filename": "recording.ogg",
    "type": models.FileTypeChoices.AUDIO_RECORDING,
    "duration_seconds": 1,
}


@pytest.fixture(name="throttle_rates")
def fixture_throttle_rates(settings, monkeypatch):
    """Override nested rates without leaking changes into other tests."""
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    monkeypatch.setitem(rates, "file_create_burst", "3/minute")
    monkeypatch.setitem(rates, "file_create_sustained", "100/hour")
    return rates


def test_api_files_throttling_default_rates():
    """Default limits allow ten creations per minute and one hundred per hour."""
    burst = FileCreateThrottleBurst()
    sustained = FileCreateThrottleSustained()

    assert (burst.num_requests, burst.duration) == (10, 60)
    assert (sustained.num_requests, sustained.duration) == (100, 3600)


@pytest.mark.parametrize(
    "burst,sustained,duration",
    [("3/minute", "100/hour", 60), ("100/minute", "3/hour", 3600)],
)
def test_api_files_throttling_limits_and_expiry(
    throttle_rates, burst, sustained, duration
):
    """Each configured limit rejects excess creations until its window expires."""
    throttle_rates.update(file_create_burst=burst, file_create_sustained=sustained)
    client = APIClient()
    client.force_login(factories.UserFactory())

    with mock.patch("rest_framework.throttling.SimpleRateThrottle.timer") as timer:
        timer.return_value = 10000
        for _ in range(3):
            response = client.post(URL, PAYLOAD, format="json")
            assert response.status_code == 201, response.json()

        response = client.post(URL, PAYLOAD, format="json")

        assert response.status_code == 429
        assert int(response["Retry-After"]) == duration
        assert models.File.objects.count() == 3

        timer.return_value += duration
        response = client.post(URL, PAYLOAD, format="json")

        assert response.status_code == 201, response.json()
        assert models.File.objects.count() == 4


@pytest.mark.usefixtures("throttle_rates")
def test_api_files_throttling_is_per_user():
    """Users sharing an IP address have independent creation allowances."""
    client = APIClient()
    client.force_login(factories.UserFactory())

    for _ in range(3):
        assert client.post(URL, PAYLOAD, format="json").status_code == 201
    assert client.post(URL, PAYLOAD, format="json").status_code == 429

    client.force_login(factories.UserFactory())

    assert client.post(URL, PAYLOAD, format="json").status_code == 201


@pytest.mark.usefixtures("throttle_rates")
def test_api_files_throttling_other_actions_not_throttled():
    """An exhausted creation allowance leaves other file actions available."""
    client = APIClient()
    client.force_login(factories.UserFactory())

    for _ in range(3):
        response = client.post(URL, PAYLOAD, format="json")
        assert response.status_code == 201
    assert client.post(URL, PAYLOAD, format="json").status_code == 429

    detail_url = f"{URL}{response.json()['id']}/"
    for _ in range(4):
        assert client.get(URL).status_code == 200
        assert client.get(detail_url).status_code == 200
    assert (
        client.patch(detail_url, {"title": "Updated"}, format="json").status_code == 200
    )


def test_api_files_throttling_sustained_across_bursts(throttle_rates):
    """The hourly allowance persists when the minute allowance resets."""
    throttle_rates.update(file_create_burst="2/minute", file_create_sustained="3/hour")
    client = APIClient()
    client.force_login(factories.UserFactory())

    with mock.patch("rest_framework.throttling.SimpleRateThrottle.timer") as timer:
        timer.return_value = 10000
        for _ in range(2):
            assert client.post(URL, PAYLOAD, format="json").status_code == 201

        timer.return_value += 60
        assert client.post(URL, PAYLOAD, format="json").status_code == 201
        assert client.post(URL, PAYLOAD, format="json").status_code == 429

    assert models.File.objects.count() == 3
