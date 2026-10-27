"""PKCE brute-force protection counts failures against the originating IP."""

from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from django.core.cache import cache
from django.test import RequestFactory

import pytest
from mozilla_django_oidc.utils import generate_code_challenge
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView

from core.authentication.proxies import _trusted_networks
from core.authentication.throttling import (
    FailedRequestThrottleMixin,
    PKCETokenExchangeThrottle,
    get_client_ip,
)
from core.authentication.views import get_pkce_authorization_code_cache_key
from core.factories import MobileAuthSessionFactory, UserFactory

from dictaphone.settings import Base

URL = "/api/v1.0/oauth/token/"
PAYLOAD = {"code": "a" * 43, "code_verifier": "b" * 43}


@pytest.fixture(name="timer", autouse=True)
def fixture_timer(settings, monkeypatch):
    """Use an isolated cache and a small allowance with a deterministic clock."""
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    monkeypatch.setitem(rates, PKCETokenExchangeThrottle.scope, "2/minute")
    settings.AUTH_PKCE_TRUSTED_PROXIES = []
    cache.clear()
    with mock.patch.object(
        PKCETokenExchangeThrottle, "timer", return_value=120
    ) as timer:
        yield timer
    cache.clear()


def send(client=None, **extra):
    """Send an otherwise well-formed exchange with an unknown code."""
    return (client or APIClient()).post(URL, PAYLOAD, format="json", **extra)


@pytest.mark.parametrize("response_status", [200, 400, 403, 429, 500])
def test_mixin_counts_only_client_errors_on_another_view(response_status):
    """Reusing the mixin counts client failures while excluding success, 429 and 5xx."""

    class ExampleView(FailedRequestThrottleMixin, APIView):
        """An independent API view using the same IP throttle."""

        authentication_classes = []
        permission_classes = []
        throttle_classes = [PKCETokenExchangeThrottle]

        def post(self, request):
            """Return the status whose effect on the failure allowance is tested."""
            return Response(status=response_status)

    view = ExampleView.as_view()
    factory = APIRequestFactory()
    for _ in range(2):
        assert view(factory.post(URL)).status_code == response_status
    expected = 429 if response_status in (400, 403) else response_status
    assert view(factory.post(URL)).status_code == expected


def test_failures_limit_and_expire(timer, caplog):
    """Failed exchanges block the next request and log the IP without credentials."""
    assert send().status_code == 400
    assert send().status_code == 400
    response = send()
    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert "127.0.0.1" in caplog.text
    assert "rate limit reached" in caplog.text
    assert PAYLOAD["code"] not in caplog.text
    timer.return_value = 150
    assert send()["Retry-After"] == "30"
    timer.return_value = 180
    assert send().status_code == 400


@pytest.mark.parametrize(
    "payload,content_type",
    [({}, "application/json"), ("{", "application/json")],
)
def test_malformed_requests_count(payload, content_type):
    """Schema validation and JSON parser errors also consume the allowance."""
    client = APIClient()
    for _ in range(2):
        assert client.post(URL, payload, content_type=content_type).status_code == 400
    assert send(client).status_code == 429


def test_unsupported_media_type_counts():
    """Client errors outside schema validation also count as failed attempts."""
    client = APIClient()
    for _ in range(2):
        assert client.post(URL, "invalid", content_type="text/plain").status_code == 415
    assert send(client).status_code == 429


def test_ip_isolation_and_untrusted_headers():
    """Rotating spoofed headers cannot bypass a direct client's allowance."""
    for spoofed in ["192.0.2.10", "192.0.2.11"]:
        assert send(HTTP_X_FORWARDED_FOR=spoofed).status_code == 400
    assert send(HTTP_X_FORWARDED_FOR="192.0.2.12").status_code == 429
    assert send(REMOTE_ADDR="192.0.2.20").status_code == 400


def test_trusted_proxy_uses_client_ip(settings):
    """Clients behind a trusted proxy have separate counters, ignoring spoofed prefixes."""
    settings.AUTH_PKCE_TRUSTED_PROXIES = ["10.0.0.0/8"]
    for prefix in ["192.0.2.1", "192.0.2.2"]:
        assert (
            send(
                REMOTE_ADDR="10.0.0.1",
                HTTP_X_FORWARDED_FOR=f"{prefix}, 198.51.100.1, 10.0.0.2",
            ).status_code
            == 400
        )
    assert (
        send(REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="198.51.100.1").status_code
        == 429
    )
    assert (
        send(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.2").status_code
        == 400
    )


@pytest.mark.parametrize(
    "peer,forwarded,expected",
    [
        ("192.0.2.1", "198.51.100.1", "192.0.2.1"),
        ("10.0.0.1", "bad, 198.51.100.1", "198.51.100.1"),
        ("10.0.0.1", "bad, 10.0.0.2", "10.0.0.2"),
        ("10.0.0.1", "198.51.100.1, bad, 10.0.0.2", "10.0.0.2"),
        ("10.0.0.1", "198.51.100.1, bad", "10.0.0.1"),
        ("invalid", "198.51.100.1", "unknown"),
        ("10.0.0.1", "", "10.0.0.1"),
        ("2001:db8::1", "2001:0db8:1::1", "2001:db8:1::1"),
        ("::ffff:192.0.2.1", "", "192.0.2.1"),
        ("::ffff:10.0.0.1", "198.51.100.1", "198.51.100.1"),
    ],
)
def test_client_ip_normalization(settings, peer, forwarded, expected):
    """Canonicalize IPv6 addresses and fall back safely for malformed headers."""
    settings.AUTH_PKCE_TRUSTED_PROXIES = ["10.0.0.0/8", "2001:db8::/48"]
    request = RequestFactory().post(
        URL, REMOTE_ADDR=peer, HTTP_X_FORWARDED_FOR=forwarded
    )
    assert get_client_ip(request) == expected


@pytest.mark.parametrize("invalid_network", ["bad", "10.0.0.1/8", "2001:db8::1/48"])
def test_startup_rejects_invalid_trusted_proxies(monkeypatch, invalid_network):
    """Fail at startup for malformed networks or CIDRs with host bits set."""
    monkeypatch.setattr(
        Base, "AUTH_PKCE_TRUSTED_PROXIES", ["10.0.0.0/8", invalid_network]
    )
    with pytest.raises(ValueError, match="does not appear|has host bits set"):
        Base.post_setup()


def test_trusted_networks_are_reused_for_requests(settings):
    """Requests reuse the parsed tuple populated by startup validation."""
    entries = ("10.0.0.0/8", "2001:db8::/48")
    settings.AUTH_PKCE_TRUSTED_PROXIES = list(entries)
    _trusted_networks(entries)
    request = RequestFactory().post(
        URL, REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.1"
    )
    with mock.patch("core.authentication.proxies.ip_network") as parse_network:
        assert get_client_ip(request) == "198.51.100.1"
        assert get_client_ip(request) == "198.51.100.1"
    parse_network.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("failure", ["verifier", "inactive_user"])
def test_all_exchange_failures_count(failure):
    """Wrong verifiers and codes belonging to inactive users are failures too."""
    user = UserFactory(is_active=failure != "inactive_user")
    for _ in range(2):
        cache.delete(
            get_pkce_authorization_code_cache_key(PAYLOAD["code"]) + ":claimed"
        )
        cache.set(
            get_pkce_authorization_code_cache_key(PAYLOAD["code"]),
            {
                "user_id": user.pk,
                "session_id": str(MobileAuthSessionFactory(user=user).pk),
                "code_challenge": generate_code_challenge(
                    "c" * 43 if failure == "verifier" else PAYLOAD["code_verifier"],
                    "S256",
                ),
            },
        )
        assert send().status_code == 400
    assert send().status_code == 429


@pytest.mark.django_db
def test_success_neither_counts_nor_resets_failures():
    """Successful exchanges leave failures intact; blocking does not consume codes."""
    user = UserFactory()

    def set_code():
        cache.delete(
            get_pkce_authorization_code_cache_key(PAYLOAD["code"]) + ":claimed"
        )
        cache.set(
            get_pkce_authorization_code_cache_key(PAYLOAD["code"]),
            {
                "user_id": user.pk,
                "session_id": str(MobileAuthSessionFactory(user=user).pk),
                "code_challenge": generate_code_challenge(
                    PAYLOAD["code_verifier"], "S256"
                ),
            },
        )

    assert send().status_code == 400
    for _ in range(3):
        set_code()
        assert send().status_code == 200
    assert send().status_code == 400
    set_code()
    assert send().status_code == 429
    assert cache.get(get_pkce_authorization_code_cache_key(PAYLOAD["code"]))


def test_concurrent_failures_are_not_lost(settings, monkeypatch):
    """Concurrent workers increment the shared counter instead of replacing histories."""
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    monkeypatch.setitem(rates, PKCETokenExchangeThrottle.scope, "20/hour")
    request = RequestFactory().post(URL)
    throttles = [PKCETokenExchangeThrottle() for _ in range(20)]
    for throttle in throttles:
        assert throttle.allow_request(request, None)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda throttle: throttle.record_failure(), throttles))
    assert not PKCETokenExchangeThrottle().allow_request(request, None)
    assert cache.get(throttles[0].key) == 20
