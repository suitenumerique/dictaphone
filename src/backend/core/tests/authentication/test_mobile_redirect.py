"""Test mobile redirect."""

import pytest
from rest_framework.test import APIClient

from core import factories

pytestmark = pytest.mark.django_db


def test_mobile_redirect_not_authenticated():
    """
    Shouldn't send information for redirect to the mobile app if the user is not connected.
    """
    client = APIClient()

    res = client.get("/api/v1.0/mobile-redirect/")
    assert res.status_code == 401


def test_mobile_redirect_works_with_connected_user():
    """
    Should send information for redirect to the mobile app if the user is connected.
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    res = client.get("/api/v1.0/mobile-redirect/")
    assert res.status_code == 200
    content = res.content.decode()
    assert f"""const sessionKey = "{client.session.session_key}";""" in content
