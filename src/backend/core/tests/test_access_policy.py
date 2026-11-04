"""App access policy, authentication refresh, and API enforcement regressions."""

from datetime import timedelta

from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core import factories, models
from core.api.serializers import UserSerializer
from core.authentication.backends import (
    OIDCAuthenticationBackend,
    OIDCRegistrationRestricted,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "roles, allowed, restricted",
    [
        ([], [], False),
        ([], ["priviledged_user"], True),
        (["other"], ["priviledged_user"], True),
        (["other", "priviledged_user"], ["priviledged_user"], False),
    ],
)
def test_role_policy(settings, roles, allowed, restricted):
    """Any matching role grants access, and an empty policy disables the gate."""
    settings.OIDC_ALLOWED_ROLES = allowed
    assert factories.UserFactory(oidc_roles=roles).is_restricted is restricted


@pytest.mark.parametrize(
    "active, expiry, allowed",
    [
        (True, None, True),
        (False, None, False),
        (True, -1, False),
        (True, 1, True),
    ],
)
def test_email_bypass(settings, active, expiry, allowed):
    """Email bypass matching is normalized, active, and time bounded."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    entry = models.AccessBypassEmail.objects.create(
        email="  BYPASS@Example.com  ",
        is_active=active,
        expires_at=timezone.now() + timedelta(days=expiry) if expiry else None,
    )
    assert entry.email == "bypass@example.com"
    user = factories.UserFactory(email="Bypass@example.com")
    assert user.is_restricted is not allowed


@pytest.mark.parametrize("roles", [None, [], "", {"priviledged_user": True}, [1]])
def test_login_clears_revoked_roles(settings, monkeypatch, roles):
    """Existing users can sign in after losing roles, with restrictions refreshed."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory(oidc_roles=["priviledged_user"])
    claims = {"sub": user.sub, "email": user.email, "roles": roles}
    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", lambda *args: claims)
    result = OIDCAuthenticationBackend().get_or_create_user("token", None, None)
    assert result == user
    assert result.is_restricted is True
    user.refresh_from_db()
    assert user.oidc_roles == ([] if roles in ([], "") else None)


@pytest.mark.parametrize("roles", [None, [], "other", {"invalid": True}])
def test_restricted_new_user_is_not_created(settings, monkeypatch, roles):
    """Missing, malformed, or nonmatching roles cannot create an account."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    monkeypatch.setattr(
        OIDCAuthenticationBackend,
        "get_userinfo",
        lambda *args: {
            "sub": "new-user",
            "email": "new@example.com",
            "roles": roles,
        },
    )
    with pytest.raises(OIDCRegistrationRestricted):
        OIDCAuthenticationBackend().get_or_create_user("token", None, None)
    assert not models.User.objects.exists()


@pytest.mark.parametrize("grant", ["role", "bypass", "disabled"])
def test_allowed_new_user_is_created(settings, monkeypatch, grant):
    """Apply the same policy and email exceptions before persisting new users."""
    settings.OIDC_ALLOWED_ROLES = [] if grant == "disabled" else ["priviledged_user"]
    if grant == "bypass":
        models.AccessBypassEmail.objects.create(email="new@example.com")
    monkeypatch.setattr(
        OIDCAuthenticationBackend,
        "get_userinfo",
        lambda *args: {
            "sub": "new-user",
            "email": "new@example.com",
            "roles": ["priviledged_user"] if grant == "role" else [],
        },
    )
    user = OIDCAuthenticationBackend().get_or_create_user("token", None, None)
    assert user.access_status == "allowed"
    assert models.User.objects.count() == 1


@pytest.mark.parametrize("match_email", [False, True])
def test_existing_restricted_user_can_authenticate(settings, monkeypatch, match_email):
    """Existing accounts remain accessible when found by subject or email fallback."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = True
    user = factories.UserFactory(oidc_roles=["priviledged_user"])
    monkeypatch.setattr(
        OIDCAuthenticationBackend,
        "get_userinfo",
        lambda *args: {
            "sub": "changed-sub" if match_email else user.sub,
            "email": user.email,
            "roles": [],
        },
    )
    result = OIDCAuthenticationBackend().get_or_create_user("token", None, None)
    assert result.pk == user.pk
    assert result.access_status == "restricted"
    assert models.User.objects.count() == 1


def test_user_endpoint_and_live_bypass(settings):
    """Clients see restrictions, cannot edit them, and observe bypass revocation."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)
    response = client.get("/api/v1.0/users/me/")
    assert response.status_code == 200
    assert response.json()["is_restricted"] is True
    assert response.json()["access_status"] == "unknown"
    response = client.patch(
        f"/api/v1.0/users/{user.pk}/",
        {
            "is_restricted": False,
            "access_status": "allowed",
            "oidc_roles": ["priviledged_user"],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["is_restricted"] is True
    entry = models.AccessBypassEmail.objects.create(email=user.email)
    assert client.get("/api/v1.0/users/me/").json()["is_restricted"] is False
    entry.is_active = False
    entry.save()
    assert client.get("/api/v1.0/users/me/").json()["is_restricted"] is True


@pytest.mark.parametrize("jwt", [False, True])
@pytest.mark.parametrize("action", ["create", "upload_ended", "retry"])
def test_restricted_processing_has_no_side_effects(settings, action, jwt):
    """Reject processing before issuing upload policies or scheduling work."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory()
    file = factories.FileFactory(creator=user)
    job = factories.AiFileJobFactory(file=file, status=models.AiJobStatusChoices.FAILED)
    client = APIClient()
    if jwt:
        token = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    else:
        client.force_login(user)
    paths = {
        "create": "/api/v1.0/files/",
        "upload_ended": f"/api/v1.0/files/{file.pk}/upload-ended/",
        "retry": f"/api/v1.0/ai-jobs/{job.pk}/retry/",
    }
    response = client.post(paths[action], {}, format="json")
    assert response.status_code == 403, response.content
    assert models.File.objects.count() == 1
    assert models.AiFileJob.objects.count() == 1
    job.refresh_from_db()
    assert job.status == models.AiJobStatusChoices.FAILED
    assert not models.AudioJob.objects.exists()


@pytest.mark.parametrize("grant", ["role", "bypass"])
def test_allowed_user_can_create_upload(settings, grant):
    """Both a matching role and an email exception allow issuing an upload policy."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory(
        oidc_roles=["priviledged_user"] if grant == "role" else []
    )
    if grant == "bypass":
        models.AccessBypassEmail.objects.create(email=user.email)
    client = APIClient()
    client.force_login(user)
    response = client.post(
        "/api/v1.0/files/",
        {
            "filename": "recording.ogg",
            "duration_seconds": 1,
            "type": models.FileTypeChoices.AUDIO_RECORDING,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["policy"]


def test_restricted_user_keeps_read_access(settings):
    """Restricted users can list their files and inspect the available abilities."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory()
    factories.FileFactory(creator=user)
    client = APIClient()
    client.force_login(user)
    response = client.get("/api/v1.0/files/")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["abilities"]["upload_ended"] is False


@pytest.mark.parametrize(
    "roles, status",
    [
        (None, "unknown"),
        ([], "restricted"),
        (["other"], "restricted"),
        (["priviledged_user"], "allowed"),
    ],
)
def test_access_status_contract(settings, roles, status):
    """The user API distinguishes missing role information from known access."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory(oidc_roles=roles)
    client = APIClient()
    client.force_login(user)
    response = client.get("/api/v1.0/users/me/")
    assert response.status_code == 200
    assert response.json()["access_status"] == status
    assert response.json()["is_restricted"] is (status != "allowed")


@pytest.mark.parametrize("roles", [None, []])
@pytest.mark.parametrize("action", ["create", "upload_ended", "retry"])
def test_unknown_and_restricted_access_block_processing(settings, roles, action):
    """Unknown access must never bypass processing restrictions."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory(oidc_roles=roles)
    client = APIClient()
    client.force_login(user)
    paths = {
        "create": "/api/v1.0/files/",
        "upload_ended": "/api/v1.0/files/00000000-0000-0000-0000-000000000001/upload-ended/",
        "retry": "/api/v1.0/ai-jobs/00000000-0000-0000-0000-000000000001/retry/",
    }
    response = client.post(paths[action], {}, format="json")
    assert response.status_code == 403
    # Access denial must leave the session valid, including for a recording in progress.
    response = client.get("/api/v1.0/users/me/")
    assert response.status_code == 200
    assert response.json()["access_status"] == (
        "unknown" if roles is None else "restricted"
    )


def test_reauthentication_resolves_unknown_without_logout(settings, monkeypatch):
    """A successful authentication updates an existing user's unknown status."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory()
    assert user.access_status == "unknown"
    monkeypatch.setattr(
        OIDCAuthenticationBackend,
        "get_userinfo",
        lambda *args: {
            "sub": user.sub,
            "email": user.email,
            "roles": ["priviledged_user"],
        },
    )
    result = OIDCAuthenticationBackend().get_or_create_user("token", None, None)
    assert result.pk == user.pk
    assert result.access_status == "allowed"


@pytest.mark.parametrize(
    "roles, allowed_roles, queries",
    [
        (None, [], 0),
        (["priviledged_user"], ["priviledged_user"], 0),
        ([], ["priviledged_user"], 1),
        (None, ["priviledged_user"], 1),
    ],
)
@pytest.mark.parametrize("with_request", [True, False])
def test_user_access_serialization_query_count(
    settings, roles, allowed_roles, queries, with_request
):
    """Both public access fields share one decision and skip unnecessary bypass queries."""
    settings.OIDC_ALLOWED_ROLES = allowed_roles
    user = factories.UserFactory(oidc_roles=roles)
    request = RequestFactory().get("/api/v1.0/users/me/")
    request.user = user
    context = {"request": request} if with_request else {}
    with CaptureQueriesContext(connection) as captured_queries:
        data = UserSerializer(user, context=context).data
    assert len(captured_queries) == queries
    assert data["is_restricted"] is (data["access_status"] != "allowed")


def test_file_list_only_checks_bypass_once(settings):
    """Access policy queries do not grow with the number of serialized files."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory()
    factories.FileFactory.create_batch(5, creator=user)
    client = APIClient()
    client.force_authenticate(user)
    with CaptureQueriesContext(connection) as queries:
        response = client.get("/api/v1.0/files/")
    assert response.status_code == 200
    assert response.json()["count"] == 5
    bypass_queries = [
        query
        for query in queries.captured_queries
        if "dictaphone_access_bypass_email" in query["sql"]
    ]
    assert len(bypass_queries) == 1


def test_request_cache_does_not_hide_bypass_expiration(settings):
    """Reusing a user object across requests cannot preserve an expired grant."""
    settings.OIDC_ALLOWED_ROLES = ["priviledged_user"]
    user = factories.UserFactory()
    entry = models.AccessBypassEmail.objects.create(email=user.email)
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/v1.0/users/me/").json()["access_status"] == "allowed"
    entry.expires_at = timezone.now() - timedelta(seconds=1)
    entry.save()
    assert client.get("/api/v1.0/users/me/").json()["access_status"] == "unknown"
