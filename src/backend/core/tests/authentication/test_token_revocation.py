"""Refresh token revocation for mobile logout."""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_logout_revokes_copied_refresh_without_affecting_other_sessions():
    """No access token is required to revoke a refresh token."""
    user = UserFactory()
    refresh = str(RefreshToken.for_user(user))
    other_refresh = str(RefreshToken.for_user(user))
    client = APIClient()

    response = client.post(
        "/api/v1.0/oauth/token/revoke/", {"refresh": refresh}, format="json"
    )
    assert response.status_code == 200
    response = client.post(
        "/api/v1.0/oauth/token/refresh/", {"refresh": refresh}, format="json"
    )
    assert response.status_code == 401
    response = client.post(
        "/api/v1.0/oauth/token/refresh/", {"refresh": other_refresh}, format="json"
    )
    assert response.status_code == 200


def test_refresh_rotates_once_and_replacement_can_be_revoked():
    """Rotation consumes the old token; logout consumes its replacement."""
    refresh = str(RefreshToken.for_user(UserFactory()))
    client = APIClient()
    response = client.post(
        "/api/v1.0/oauth/token/refresh/", {"refresh": refresh}, format="json"
    )
    assert response.status_code == 200
    replacement = response.json()["refresh"]
    assert replacement != refresh
    response = client.post(
        "/api/v1.0/oauth/token/refresh/", {"refresh": refresh}, format="json"
    )
    assert response.status_code == 401
    response = client.post(
        "/api/v1.0/oauth/token/revoke/", {"refresh": replacement}, format="json"
    )
    assert response.status_code == 200
    response = client.post(
        "/api/v1.0/oauth/token/refresh/", {"refresh": replacement}, format="json"
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [({}, 400), ({"refresh": "invalid"}, 401)],
)
def test_revocation_rejects_invalid_requests(payload, expected_status):
    """Malformed requests cannot successfully revoke a token."""
    response = APIClient().post("/api/v1.0/oauth/token/revoke/", payload, format="json")
    assert response.status_code == expected_status
