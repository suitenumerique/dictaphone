"""File listing refreshes analytics person properties at most once per hour."""

from unittest import mock

from django.core.cache import cache

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core import factories

pytestmark = pytest.mark.django_db
URL = "/api/v1.0/files/"


@pytest.fixture(name="analytics_settings", autouse=True)
def fixture_analytics_settings(settings):
    """Enable analytics with an isolated cache and no external PostHog calls."""
    settings.POSTHOG_ENABLED = True
    settings.OIDC_ALLOWED_ROLES = ["allowed"]
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    cache.clear()
    with mock.patch("core.analytics.posthog.capture") as capture:
        yield capture
    cache.clear()


@pytest.mark.parametrize(
    "roles, access_status",
    [(["allowed"], "allowed"), ([], "restricted"), (None, "unknown")],
)
def test_list_sets_access_status_person_property(
    analytics_settings, roles, access_status
):
    """All access statuses receive an identified person update."""
    user = factories.UserFactory(oidc_roles=roles)
    client = APIClient()
    client.force_authenticate(user)

    assert client.get(URL).status_code == 200

    analytics_settings.assert_called_once_with(
        "files_listed",
        distinct_id=user.id,
        properties={
            "client_source": "web",
            "$set": {
                "name": user.full_name,
                "email": user.email,
                "sub": user.sub,
                "access_status": access_status,
            },
        },
    )


@pytest.mark.parametrize("client_source", ["web", "mobile"])
def test_list_analytics_client_source(analytics_settings, client_source):
    """Session and JWT authentication identify the existing web and mobile clients."""
    user = factories.UserFactory()
    client = APIClient()
    if client_source == "mobile":
        token = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    else:
        client.force_login(user)

    assert client.get(URL).status_code == 200
    analytics_settings.assert_called_once()
    properties = analytics_settings.call_args.kwargs["properties"]
    assert properties["client_source"] == client_source
    assert "client_source" not in properties["$set"]


def test_list_analytics_hourly_per_user(analytics_settings):
    """Requests share an allowance per user that expires after one hour."""
    user = factories.UserFactory(oidc_roles=[])
    other_user = factories.UserFactory(oidc_roles=["allowed"])
    client = APIClient()
    client.force_authenticate(user)

    with freeze_time("2026-11-04T12:00:00Z") as clock:
        assert client.get(URL).status_code == 200
        clock.tick(3599)
        user.oidc_roles = ["allowed"]
        user.save(update_fields=["oidc_roles"])
        assert client.get(URL + "?is_creator_me=true").status_code == 200
        assert analytics_settings.call_count == 1

        # Switching clients does not grant the same user another hourly event.
        client.force_authenticate(user=None)
        token = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert client.get(URL).status_code == 200
        assert analytics_settings.call_count == 1
        client.credentials()

        client.force_authenticate(other_user)
        assert client.get(URL).status_code == 200
        assert analytics_settings.call_count == 2

        clock.tick(1)
        client.force_authenticate(user)
        assert client.get(URL).status_code == 200
        assert analytics_settings.call_count == 3
        assert analytics_settings.call_args.kwargs["distinct_id"] == user.id
        assert (
            analytics_settings.call_args.kwargs["properties"]["$set"]["access_status"]
            == "allowed"
        )


def test_list_analytics_anonymous(analytics_settings):
    """Rejected anonymous requests do not emit analytics."""
    assert APIClient().get(URL).status_code == 401
    analytics_settings.assert_not_called()


def test_list_analytics_disabled(settings, analytics_settings):
    """Disabled analytics does not consume the user's hourly allowance."""
    client = APIClient()
    client.force_authenticate(factories.UserFactory())
    settings.POSTHOG_ENABLED = False
    assert client.get(URL).status_code == 200
    analytics_settings.assert_not_called()

    settings.POSTHOG_ENABLED = True
    assert client.get(URL).status_code == 200
    analytics_settings.assert_called_once()


@pytest.mark.parametrize("failure", ["cache", "posthog"])
def test_list_analytics_failure_does_not_break_listing(failure):
    """Cache and analytics failures leave the list endpoint available."""
    client = APIClient()
    client.force_authenticate(factories.UserFactory())
    target = (
        "core.analytics.cache.add"
        if failure == "cache"
        else "core.analytics.posthog.capture"
    )
    with mock.patch(target, side_effect=RuntimeError("unavailable")):
        assert client.get(URL).status_code == 200
