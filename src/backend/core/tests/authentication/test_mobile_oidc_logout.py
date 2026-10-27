"""Provider logout is bound to the mobile login and independent of cookies."""

import json
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mozilla_django_oidc.utils import generate_code_challenge
from rest_framework.test import APIClient

from core.authentication.backends import OIDCAuthenticationBackend
from core.authentication.logout import MobileBackChannelLogoutView
from core.authentication.mobile import create_mobile_session, oidc_cipher
from core.authentication.views import get_pkce_authorization_code_cache_key
from core.factories import UserFactory
from core.models import MobileAuthSession

pytestmark = pytest.mark.django_db(transaction=True)
ISSUER = "https://idp.example/realm"
LOGOUT = "/api/v1.0/oauth/token/revoke/"


@pytest.fixture(autouse=True)
def provider_settings(settings):
    """Real shared-cache operations, isolated from other tests and deployments."""
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    settings.OIDC_OP_URL = ISSUER
    settings.OIDC_OP_LOGOUT_ENDPOINT = ISSUER + "/logout"
    settings.LOGOUT_REDIRECT_URL = "https://app.example/"
    cache.clear()
    yield
    cache.clear()


def login(user=None, **kwargs):
    """An application session linked to verified provider metadata."""
    return create_mobile_session(
        user or UserFactory(),
        oidc_issuer=ISSUER,
        oidc_sub="subject",
        oidc_sid="provider-session",
        encrypted_id_token=oidc_cipher().encrypt(b"provider-id-token").decode(),
        **kwargs,
    )


def test_logout_deletes_browser_session_before_provider_and_revokes_api_access():
    browser = Client()
    user = UserFactory()
    browser.force_login(user)
    pair = login(user, browser_session_key=browser.session.session_key)
    response = APIClient().post(LOGOUT, {"revoke": pair["revoke"]}, format="json")
    assert response.status_code == 200
    assert browser.get("/api/v1.0/users/me/").status_code == 401
    start = browser.get(response.json()["logout_url"])
    assert start.status_code == 302
    params = parse_qs(urlsplit(start.url).query)
    assert params["id_token_hint"] == ["provider-id-token"]
    assert params["post_logout_redirect_uri"] == [
        "http://testserver/api/v1.0/oauth/logout/callback/"
    ]
    assert browser.get(response.json()["logout_url"]).status_code == 400
    callback = params["post_logout_redirect_uri"][0] + "?state=" + params["state"][0]
    completed = browser.get(callback)
    assert completed.status_code == 302
    assert completed.url.endswith("?logout=1")
    assert completed["Cache-Control"] == "no-store"
    assert browser.get(callback).status_code == 400


def test_browser_logout_revokes_linked_mobile_login_before_callback():
    browser = Client()
    user = UserFactory()
    browser.force_login(user)
    session = browser.session
    session["oidc_id_token"] = "browser-id-token"
    session.save()
    login(user, browser_session_key=session.session_key)
    response = browser.get("/api/v1.0/logout/")
    assert response.status_code == 302
    assert MobileAuthSession.objects.get().revocation_reason == "browser_logout"
    assert browser.get("/api/v1.0/users/me/").status_code == 401
    start = browser.get(response.url)
    params = parse_qs(urlsplit(start.url).query)
    completed = browser.get(
        reverse("mobile_logout_callback"), {"state": params["state"][0]}
    )
    assert completed.url == "https://app.example/"


def test_provider_failure_cannot_restore_local_session(settings):
    pair = login()
    settings.OIDC_OP_LOGOUT_ENDPOINT = None
    response = APIClient().post(LOGOUT, {"revoke": pair["revoke"]}, format="json")
    assert response.json() == {"logout_url": None}
    assert MobileAuthSession.objects.get().revoked_at is not None
    assert (
        Client().get(reverse("mobile_logout_callback"), {"state": "x" * 43}).status_code
        == 400
    )


@pytest.fixture
def signed_logout(settings):
    """Exercise actual RSA signature, issuer and audience validation."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.PyJWK(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())))

    def sign(**overrides):
        now = int(timezone.now().timestamp())
        payload = {
            "iss": ISSUER,
            "aud": settings.OIDC_RP_CLIENT_ID,
            "iat": now,
            "exp": now + 60,
            "jti": "logout-event",
            "events": {MobileBackChannelLogoutView.LOGOUT_EVENT_URI: {}},
            "sub": "subject",
            "sid": "provider-session",
        }
        payload.update(overrides)
        return jwt.encode(payload, key, algorithm="RS256")

    with mock.patch(
        "lasuite.oidc_login.views.OIDCAuthenticationBackend.retrieve_matching_jwk",
        return_value=jwk,
    ):
        yield sign


def test_signed_backchannel_logout_targets_provider_session_and_detects_replay(
    signed_logout,
):
    login()
    login()
    user = UserFactory()
    create_mobile_session(
        user, oidc_issuer=ISSUER, oidc_sub="subject", oidc_sid="other"
    )
    create_mobile_session(
        user,
        oidc_issuer="https://other.example",
        oidc_sub="subject",
        oidc_sid="provider-session",
    )
    token = signed_logout()
    client = Client()
    response = client.post("/api/v1.0/backchannel-logout/", {"logout_token": token})
    assert response.status_code == 204
    assert MobileAuthSession.objects.filter(revoked_at__isnull=False).count() == 2
    assert (
        client.post(
            "/api/v1.0/backchannel-logout/", {"logout_token": token}
        ).status_code
        == 400
    )


def test_subject_only_backchannel_revokes_all_subject_sessions(signed_logout):
    login()
    create_mobile_session(
        UserFactory(), oidc_issuer=ISSUER, oidc_sub="subject", oidc_sid="other"
    )
    create_mobile_session(UserFactory(), oidc_issuer=ISSUER, oidc_sub="unrelated")
    payload = signed_logout(sid=None)
    assert (
        Client()
        .post("/api/v1.0/backchannel-logout/", {"logout_token": payload})
        .status_code
        == 204
    )
    assert MobileAuthSession.objects.filter(revoked_at__isnull=False).count() == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://attacker.example"},
        {"aud": "another-client"},
        {"nonce": "forbidden"},
        {"events": {}},
        {"jti": None},
        {"iat": 1, "exp": 9999999999},
        {"sub": None, "sid": None},
    ],
)
def test_invalid_backchannel_never_revokes(overrides, signed_logout):
    login()
    response = Client().post(
        "/api/v1.0/backchannel-logout/", {"logout_token": signed_logout(**overrides)}
    )
    assert response.status_code == 400
    assert MobileAuthSession.objects.get().revoked_at is None


def test_id_token_encryption_supports_secret_rotation(settings):
    encrypted = oidc_cipher().encrypt(b"sensitive").decode()
    assert "sensitive" not in encrypted
    settings.SECRET_KEY_FALLBACKS = [settings.SECRET_KEY]
    settings.SECRET_KEY = "replacement-secret"
    assert oidc_cipher().decrypt(encrypted.encode()) == b"sensitive"


def test_browser_cache_failure_cannot_rollback_application_revocation():
    pair = login(browser_session_key="deleted-browser-session")
    with mock.patch(
        "django.contrib.sessions.backends.cache.SessionStore.delete",
        side_effect=RuntimeError("Cache unavailable"),
    ):
        response = APIClient().post(LOGOUT, {"revoke": pair["revoke"]}, format="json")
    assert response.status_code == 200
    assert MobileAuthSession.objects.get().revoked_at is not None


def test_provider_logout_invalidates_a_pending_pkce_code(signed_logout):
    login()
    session = MobileAuthSession.objects.get()
    session.refresh_jti = ""
    session.save()
    code = "c" * 43
    verifier = "v" * 43
    cache.set(
        get_pkce_authorization_code_cache_key(code),
        {
            "user_id": session.user_id,
            "session_id": str(session.pk),
            "code_challenge": generate_code_challenge(verifier, "S256"),
        },
    )
    assert (
        Client()
        .post("/api/v1.0/backchannel-logout/", {"logout_token": signed_logout()})
        .status_code
        == 204
    )
    assert (
        APIClient()
        .post(
            "/api/v1.0/oauth/token/",
            {"code": code, "code_verifier": verifier},
            format="json",
        )
        .status_code
        == 400
    )


def test_provider_metadata_comes_from_id_token_and_survives_signed_userinfo():
    backend = OIDCAuthenticationBackend()
    backend.request = RequestFactory().get("/")
    backend.request.session = {}
    claims = {"iss": ISSUER, "sub": "subject", "sid": "verified-id-token-session"}
    with mock.patch(
        "lasuite.oidc_login.backends.OIDCAuthenticationBackend.verify_token",
        return_value=claims,
    ):
        backend.verify_token("id-token", nonce="verified-nonce")
    with mock.patch(
        "lasuite.oidc_login.backends.OIDCAuthenticationBackend.verify_token",
        return_value={"sub": "subject"},
    ):
        backend.verify_token("signed-userinfo")
    assert backend.request.session["mobile_oidc_context"] == {
        "oidc_issuer": ISSUER,
        "oidc_sub": "subject",
        "oidc_sid": "verified-id-token-session",
    }
