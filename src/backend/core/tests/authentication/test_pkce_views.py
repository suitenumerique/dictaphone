"""Tests for PKCE/OIDC authentication views and OAuth token endpoints."""

from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.test import RequestFactory
from django.urls import reverse

import pytest
from mozilla_django_oidc.utils import generate_code_challenge
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.authentication.backends import OIDCAuthenticationBackend
from core.authentication.views import (
    OIDCAuthenticationCallbackWithPkceView,
    PKCEOIDCAuthenticationRequestView,
    get_pkce_authorization_code_cache_key,
)
from core.factories import UserFactory
from core.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_auth_cache(settings):
    """Keep authorization codes and failed-attempt counters isolated per test."""
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    cache.clear()
    yield
    cache.clear()


def _attach_session(request):
    """Attach a working session to a request-factory request."""
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()


def test_pkce_oidc_authentication_request_view_stores_pkce_data():
    """Should store PKCE data in session when response_type is code."""
    code_challenge = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    state = "NhnR1y7iA2aCrh3Ic5_6wD9rI3C-N3fDNzxt3wti7e1"
    request = RequestFactory().get(
        "/api/v1.0/authenticate/",
        {
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        },
    )
    _attach_session(request)

    with mock.patch(
        "core.authentication.views.OIDCAuthenticationRequestView.get",
        return_value=HttpResponseRedirect("https://sso.example/authorize"),
    ):
        response = PKCEOIDCAuthenticationRequestView().get(request)

    assert response.status_code == status.HTTP_302_FOUND
    assert request.session["pkce_oidc_response_type"] == "code"
    assert request.session["pkce_oidc_data"] == {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }


def test_pkce_oidc_authentication_request_view_invalid_parameters():
    """Should return 400 when PKCE params are invalid."""
    request = RequestFactory().get(
        "/api/v1.0/authenticate/",
        {
            "response_type": "code",
            "code_challenge": "too-short",
            "state": "also-too-short",
        },
    )
    _attach_session(request)

    with mock.patch(
        "core.authentication.views.OIDCAuthenticationRequestView.get",
        return_value=HttpResponseRedirect("https://sso.example/authorize"),
    ):
        response = PKCEOIDCAuthenticationRequestView().get(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Invalid pkce request parameters."


@pytest.mark.parametrize(
    ("length", "expected_status"),
    [(43, status.HTTP_302_FOUND), (128, status.HTTP_302_FOUND)],
)
def test_pkce_oidc_authentication_request_view_pkce_length_boundaries_are_valid(
    length, expected_status
):
    """Should accept PKCE request fields at min/max allowed lengths."""
    code_challenge = "a" * length
    state = "b" * length
    request = RequestFactory().get(
        "/api/v1.0/authenticate/",
        {
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        },
    )
    _attach_session(request)

    with mock.patch(
        "core.authentication.views.OIDCAuthenticationRequestView.get",
        return_value=HttpResponseRedirect("https://sso.example/authorize"),
    ):
        response = PKCEOIDCAuthenticationRequestView().get(request)

    assert response.status_code == expected_status
    assert request.session["pkce_oidc_data"] == {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }


@pytest.mark.parametrize(
    ("field_name", "length"),
    [
        ("code_challenge", 42),
        ("code_challenge", 129),
        ("state", 42),
        ("state", 129),
    ],
)
def test_pkce_oidc_authentication_request_view_rejects_out_of_bounds_lengths(
    field_name, length
):
    """Should reject PKCE request fields shorter/longer than allowed."""
    params = {
        "response_type": "code",
        "code_challenge": "a" * 43,
        "code_challenge_method": "S256",
        "state": "b" * 43,
    }
    params[field_name] = "c" * length
    request = RequestFactory().get("/api/v1.0/authenticate/", params)
    _attach_session(request)

    with mock.patch(
        "core.authentication.views.OIDCAuthenticationRequestView.get",
        return_value=HttpResponseRedirect("https://sso.example/authorize"),
    ):
        response = PKCEOIDCAuthenticationRequestView().get(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Invalid pkce request parameters."
    assert any(error["loc"] == (field_name,) for error in response.data["errors"])


def test_pkce_oidc_authentication_request_view_non_code_response_type():
    """Should leave session untouched when response_type is not code."""
    request = RequestFactory().get(
        "/api/v1.0/authenticate/",
        {"response_type": "token"},
    )
    _attach_session(request)

    with mock.patch(
        "core.authentication.views.OIDCAuthenticationRequestView.get",
        return_value=HttpResponseRedirect("https://sso.example/authorize"),
    ):
        response = PKCEOIDCAuthenticationRequestView().get(request)

    assert response.status_code == status.HTTP_302_FOUND
    assert "pkce_oidc_response_type" not in request.session
    assert "pkce_oidc_data" not in request.session


def test_oidc_callback_with_pkce_login_success_returns_mobile_redirect(settings):
    """Should cache auth code and redirect to mobile deep-link URL."""
    user = UserFactory()
    request = RequestFactory().get("/api/v1.0/callback/")
    _attach_session(request)

    code_challenge = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    state = "NhnR1y7iA2aCrh3Ic5_6wD9rI3C-N3fDNzxt3wti7e1"
    request.session["pkce_oidc_response_type"] = "code"
    request.session["pkce_oidc_data"] = {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    request.session.save()

    view = OIDCAuthenticationCallbackWithPkceView()
    view.request = request
    view.user = user

    with (
        mock.patch(
            "core.authentication.views.OIDCAuthenticationCallbackView.login_success",
            return_value=HttpResponseRedirect("/mobile-login"),
        ),
        mock.patch(
            "core.authentication.views.secrets.token_urlsafe",
            return_value="code",
        ),
    ):
        response = view.login_success()

    assert response.status_code == status.HTTP_302_FOUND
    assert response.url.startswith(settings.MOBILE_DEEP_LINK_SCHEME)
    assert "code=code" in response.url
    assert f"state={state}" in response.url

    cached = cache.get(get_pkce_authorization_code_cache_key("code"))
    assert cached == {
        "user_id": user.pk,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }


def test_oidc_callback_with_pkce_login_success_non_mobile_redirect_fails():
    """Should fallback to failure when callback URL is not the mobile login URL."""
    user = UserFactory()
    request = RequestFactory().get("/api/v1.0/callback/")
    _attach_session(request)
    request.session["pkce_oidc_response_type"] = "code"

    code_challenge = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    state = "NhnR1y7iA2aCrh3Ic5_6wD9rI3C-N3fDNzxt3wti7e1"
    request.session["pkce_oidc_data"] = {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    request.session.save()

    view = OIDCAuthenticationCallbackWithPkceView()
    view.request = request
    view.user = user

    with (
        mock.patch(
            "core.authentication.views.OIDCAuthenticationCallbackView.login_success",
            return_value=HttpResponseRedirect("/somewhere-else"),
        ),
        mock.patch.object(
            OIDCAuthenticationCallbackWithPkceView,
            "login_failure",
            return_value=HttpResponseRedirect("/failure"),
        ),
    ):
        response = view.login_success()

    assert response.status_code == status.HTTP_302_FOUND
    assert response.url == "/failure"


def test_oidc_callback_with_pkce_login_success_without_pkce_data_fails():
    """Should fallback to login failure when PKCE data is missing from session."""
    user = UserFactory()
    request = RequestFactory().get("/api/v1.0/callback/")
    _attach_session(request)
    request.session["pkce_oidc_response_type"] = "code"
    request.session.save()

    view = OIDCAuthenticationCallbackWithPkceView()
    view.request = request
    view.user = user

    with (
        mock.patch(
            "core.authentication.views.OIDCAuthenticationCallbackView.login_success",
            return_value=HttpResponseRedirect("/mobile-login"),
        ),
        mock.patch.object(
            OIDCAuthenticationCallbackWithPkceView,
            "login_failure",
            return_value=HttpResponseRedirect("/failure"),
        ),
    ):
        response = view.login_success()

    assert response.status_code == status.HTTP_302_FOUND
    assert response.url == "/failure"


def test_oauth_token_exchange_success_and_single_use():
    """Should exchange a valid auth code once for JWT tokens."""
    user = UserFactory()
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    code = "my-auth-code-at-least-43-characters-like-really"
    cache.set(
        get_pkce_authorization_code_cache_key(code),
        {
            "user_id": user.pk,
            "code_challenge": generate_code_challenge(verifier, "S256"),
            "code_challenge_method": "S256",
        },
        timeout=120,
    )

    client = APIClient()
    response = client.post(
        "/api/v1.0/oauth/token/",
        {"code": code, "code_verifier": verifier},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert set(response.json()) == {"refresh", "access"}

    second_try = client.post(
        "/api/v1.0/oauth/token/",
        {"code": code, "code_verifier": verifier},
        format="json",
    )
    assert second_try.status_code == status.HTTP_400_BAD_REQUEST
    assert second_try.json() == {"detail": "Invalid or expired authorization code."}


def test_oauth_token_exchange_invalid_code_verifier_consumes_code():
    """Should reject invalid verifier and consume the auth code."""
    user = UserFactory()
    code = "my-auth-code-at-least-43-characters-like-really-2"
    cache.set(
        get_pkce_authorization_code_cache_key(code),
        {
            "user_id": user.pk,
            "code_challenge": generate_code_challenge(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "S256"
            ),
            "code_challenge_method": "S256",
        },
        timeout=120,
    )

    client = APIClient()
    response = client.post(
        "/api/v1.0/oauth/token/",
        {
            "code": code,
            "code_verifier": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "Invalid code_verifier."}
    assert cache.get(get_pkce_authorization_code_cache_key(code)) is None


@pytest.mark.parametrize(
    ("field_name", "length"),
    [
        ("code", 42),
        ("code", 129),
        ("code_verifier", 42),
        ("code_verifier", 129),
    ],
)
def test_oauth_token_exchange_rejects_out_of_bounds_lengths(field_name, length):
    """Should reject PKCE token exchange fields shorter/longer than allowed."""
    payload = {
        "code": "a" * 43,
        "code_verifier": "b" * 43,
    }
    payload[field_name] = "c" * length

    client = APIClient()
    response = client.post("/api/v1.0/oauth/token/", payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["detail"] == "Invalid pkce request parameters."
    assert any(error["loc"] == [field_name] for error in data["errors"])


def test_oauth_token_refresh_endpoint_returns_access_token():
    """Should issue a new access token from a valid refresh token."""
    user = UserFactory()
    refresh = RefreshToken.for_user(user)

    client = APIClient()
    response = client.post(
        "/api/v1.0/oauth/token/refresh/",
        {"refresh": str(refresh)},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.json()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("flow", ["web", "mobile", "silent"])
@pytest.mark.parametrize("roles", [None, ["other"]])
def test_signup_restriction_callback(settings, monkeypatch, existing, flow, roles):
    """Reject new identities across login flows, preserving existing-user sessions."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    settings.LOGIN_REDIRECT_URL = "https://app.example/"
    settings.LOGIN_REDIRECT_URL_FAILURE = "https://app.example/failure"
    settings.MOBILE_DEEP_LINK_SCHEME = "dictaphone://"
    user = UserFactory(sub="login-user") if existing else None
    claims = {
        "sub": "login-user",
        "email": "login@example.com",
        "roles": roles,
        "siret": "12345678901234",
    }
    restriction_log = mock.Mock()
    monkeypatch.setattr("core.authentication.backends.logger.info", restriction_log)
    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", lambda *args: claims)

    def authenticate(backend, request, **kwargs):
        return backend.get_or_create_user("token", None, None)

    monkeypatch.setattr(OIDCAuthenticationBackend, "authenticate", authenticate)
    client = APIClient()
    session = client.session
    session["oidc_states"] = {"login-state": {"nonce": "login-nonce"}}
    session["oidc_login_next"] = (
        "https://app.example/mobile-login"
        if flow == "mobile"
        else "https://app.example/"
    )
    if flow == "silent":
        session["silent"] = True
    if flow == "mobile":
        session["pkce_oidc_response_type"] = "code"
        session["pkce_oidc_data"] = {
            "code_challenge": "a" * 43,
            "code_challenge_method": "S256",
            "state": "mobile-state",
        }
    session.save()
    response = client.get(
        reverse("oidc_authentication_callback"),
        {
            "code": "provider-code",
            "state": "login-state",
        },
    )
    assert response.status_code == 302
    assert User.objects.count() == int(existing)
    if not existing:
        restriction_log.assert_called_once_with(
            "OIDC registration restricted: sub=%s, siret=%s, email=%s, roles=%s",
            "login-user",
            "12345678901234",
            "login@example.com",
            roles,
        )
        assert response.url == "https://app.example/restricted?access_denied=1"
        assert "_auth_user_id" not in client.session
        assert not OutstandingToken.objects.exists()
        return
    restriction_log.assert_not_called()
    assert client.session["_auth_user_id"] == str(user.pk)
    if flow == "mobile":
        assert urlsplit(response.url).scheme == "dictaphone"
        params = parse_qs(urlsplit(response.url).query)
        assert params["state"] == ["mobile-state"]
        assert (
            cache.get(get_pkce_authorization_code_cache_key(params["code"][0]))[
                "user_id"
            ]
            == user.pk
        )
    else:
        assert response.url == "https://app.example/"
    response = client.get("/api/v1.0/users/me/")
    assert response.status_code == 200
    assert response.json()["access_status"] == (
        "unknown" if roles is None else "restricted"
    )
