"""A mobile login is the revocation boundary for every descendant JWT."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.core.cache import cache
from django.db import close_old_connections, connection
from django.utils import timezone

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from core.authentication.mobile import create_mobile_session
from core.factories import UserFactory
from core.models import MobileAuthSession

pytestmark = pytest.mark.django_db
REFRESH = "/api/v1.0/oauth/token/refresh/"
LOGOUT = "/api/v1.0/oauth/token/revoke/"
ME = "/api/v1.0/users/me/"


@pytest.fixture(autouse=True)
def auth_cache(settings):
    """Avoid touching the deployed session cache."""
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    cache.clear()
    yield
    cache.clear()


def post(url, data):
    """Public endpoints authenticate signed body credentials, never cookies."""
    return APIClient().post(url, data, format="json")


def access_status(access, path=ME):
    """Exercise the real global authentication class."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client.get(path).status_code


def test_logout_revokes_access_and_every_refresh_descendant_only_for_this_login():
    user = UserFactory()
    original = create_mobile_session(user)
    other = create_mobile_session(user)
    replacement = post(REFRESH, {"refresh": original["refresh"]}).json()
    assert access_status(original["access"]) == 200
    assert post(LOGOUT, {"refresh": original["refresh"]}).status_code == 200
    assert post(LOGOUT, {"revoke": original["revoke"]}).status_code == 200
    for pair in (original, replacement):
        assert access_status(pair["access"]) == 401
        assert access_status(pair["access"], "/api/v1.0/files/") == 401
        assert post(REFRESH, {"refresh": pair["refresh"]}).status_code == 401
    assert access_status(other["access"]) == 200
    assert post(REFRESH, {"refresh": other["refresh"]}).status_code == 200


def test_reusing_stolen_refresh_revokes_attackers_replacement():
    pair = create_mobile_session(UserFactory())
    attacker = post(REFRESH, {"refresh": pair["refresh"]}).json()
    assert post(REFRESH, {"refresh": pair["refresh"]}).status_code == 401
    assert access_status(attacker["access"]) == 401
    assert post(REFRESH, {"refresh": attacker["refresh"]}).status_code == 401
    assert MobileAuthSession.objects.get().revocation_reason == "refresh_reuse"


def test_logout_only_credential_cannot_access_api_or_refresh():
    pair = create_mobile_session(UserFactory())
    assert access_status(pair["revoke"]) == 401
    assert post(REFRESH, {"refresh": pair["revoke"]}).status_code == 401
    assert post(LOGOUT, {"revoke": pair["revoke"]}).status_code == 200
    assert access_status(pair["access"]) == 401


def test_logout_works_with_expired_access_and_invalid_authorization_header():
    pair = create_mobile_session(UserFactory())
    access = AccessToken(pair["access"])
    access.set_exp(lifetime=timedelta(seconds=-1))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert (
        client.post(LOGOUT, {"revoke": pair["revoke"]}, format="json").status_code
        == 200
    )
    assert access_status(pair["access"]) == 401


def test_legacy_tokens_cannot_access_or_refresh():
    legacy = RefreshToken.for_user(UserFactory())
    assert access_status(str(legacy.access_token)) == 401
    assert post(REFRESH, {"refresh": str(legacy)}).status_code == 401
    assert post(LOGOUT, {"refresh": str(legacy)}).status_code == 401


def test_session_expiry_and_disabled_user_are_enforced():
    user = UserFactory()
    pair = create_mobile_session(user)
    MobileAuthSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert access_status(pair["access"]) == 401
    assert post(REFRESH, {"refresh": pair["refresh"]}).status_code == 401
    other = create_mobile_session(user)
    user.is_active = False
    user.save()
    assert access_status(other["access"]) == 401
    assert post(REFRESH, {"refresh": other["refresh"]}).status_code == 401


def test_rotation_does_not_extend_absolute_session_expiry():
    pair = create_mobile_session(UserFactory())
    session = MobileAuthSession.objects.get()
    session.expires_at = timezone.now() + timedelta(seconds=90)
    session.save()
    replacement = post(REFRESH, {"refresh": pair["refresh"]}).json()
    for token in (
        RefreshToken(replacement["refresh"]),
        AccessToken(replacement["access"]),
    ):
        assert token["exp"] <= int(session.expires_at.timestamp())
    session.refresh_from_db()
    assert session.expires_at < timezone.now() + timedelta(seconds=91)


@pytest.mark.parametrize(
    "payload,status",
    [
        ({}, 400),
        ({"refresh": "invalid"}, 401),
        ({"revoke": "invalid"}, 401),
        ({"refresh": "a", "revoke": "b"}, 400),
    ],
)
def test_revocation_rejects_invalid_requests(payload, status):
    assert post(LOGOUT, payload).status_code == status


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("race", ["logout", "refresh"])
def test_refresh_races_are_serialized(race):
    """Real row locks prevent a successful refresh escaping concurrent revocation."""
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    pair = create_mobile_session(UserFactory())
    barrier = Barrier(2)

    def request(url, data):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            response = post(url, data)
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request, REFRESH, {"refresh": pair["refresh"]})
        second = pool.submit(
            request,
            LOGOUT if race == "logout" else REFRESH,
            {"revoke": pair["revoke"]}
            if race == "logout"
            else {"refresh": pair["refresh"]},
        )
        results = [first.result(timeout=20), second.result(timeout=20)]
    if race == "refresh":
        assert sorted(status for status, _ in results) == [200, 401]
    else:
        assert results[1][0] == 200
    assert MobileAuthSession.objects.get().revoked_at is not None
    assert access_status(pair["access"]) == 401
    for _, result in results:
        if "access" in result:
            assert access_status(result["access"]) == 401


def test_media_authorization_rejects_a_copied_access_token_after_logout():
    from core.factories import FileFactory  # noqa: PLC0415
    from core.models import FileTypeChoices, FileUploadStateChoices  # noqa: PLC0415

    user = UserFactory()
    file = FileFactory(
        creator=user,
        type=FileTypeChoices.AUDIO_RECORDING,
        update_upload_state=FileUploadStateChoices.READY,
    )
    pair = create_mobile_session(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair['access']}")
    params = {"HTTP_X_ORIGINAL_URL": f"http://localhost/media/{file.file_key}"}
    assert client.get("/api/v1.0/files/media-auth/", **params).status_code == 200
    assert post(LOGOUT, {"revoke": pair["revoke"]}).status_code == 200
    assert client.get("/api/v1.0/files/media-auth/", **params).status_code == 401


def test_admin_revocation_targets_selected_sessions_or_all_selected_users():
    from django.contrib.admin import site  # noqa: PLC0415

    from core.admin import MobileAuthSessionAdmin  # noqa: PLC0415

    user = UserFactory()
    first = create_mobile_session(user)
    second = create_mobile_session(user)
    unrelated = create_mobile_session(UserFactory())
    first_session = MobileAuthSession.objects.get(
        pk=AccessToken(first["access"])["mobile_session_id"]
    )
    selected = MobileAuthSession.objects.filter(pk=first_session.pk)
    model_admin = MobileAuthSessionAdmin(MobileAuthSession, site)
    model_admin.revoke_selected_sessions(None, selected)
    assert access_status(first["access"]) == 401
    assert access_status(second["access"]) == 200
    model_admin.revoke_all_sessions_for_users(None, selected)
    assert access_status(second["access"]) == 401
    assert access_status(unrelated["access"]) == 200


def test_cleanup_keeps_unexpired_revoked_sessions():
    from django.core.management import call_command  # noqa: PLC0415

    expired = create_mobile_session(UserFactory())
    active = create_mobile_session(UserFactory())
    revoked = create_mobile_session(UserFactory())
    post(LOGOUT, {"revoke": revoked["revoke"]})
    expired_id = AccessToken(expired["access"])["mobile_session_id"]
    MobileAuthSession.objects.filter(pk=expired_id).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    call_command("purge_mobile_sessions")
    assert not MobileAuthSession.objects.filter(pk=expired_id).exists()
    assert MobileAuthSession.objects.count() == 2
    assert access_status(active["access"]) == 200
    assert access_status(revoked["access"]) == 401
