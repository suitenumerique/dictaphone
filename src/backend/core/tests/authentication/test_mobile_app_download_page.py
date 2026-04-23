"""Test mobile app download page redirects."""

from urllib.parse import urljoin

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "user_agent",
    [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)",
        "my custom IOS app browser",
    ],
)
def test_download_mobile_app_redirects_to_ios_link(user_agent, settings):
    """Should redirect iOS user agents to the iOS mobile app link."""
    settings.MOBILE_APP_IOS_DOWNLOAD_LINK = "https://apps.apple.com/app/example-ios"
    client = APIClient()

    res = client.get(
        "/api/v1.0/download-mobile-app/",
        HTTP_USER_AGENT=user_agent,
    )

    assert res.status_code == 302
    assert res["Location"] == settings.MOBILE_APP_IOS_DOWNLOAD_LINK


def test_download_mobile_app_redirects_to_android_link(settings):
    """Should redirect Android user agents to the Android mobile app link."""
    settings.MOBILE_APP_ANDROID_DOWNLOAD_LINK = (
        "https://play.google.com/store/apps/details?id=example.android"
    )
    client = APIClient()

    res = client.get(
        "/api/v1.0/download-mobile-app/",
        HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14; Pixel 8)",
    )

    assert res.status_code == 302
    assert res["Location"] == settings.MOBILE_APP_ANDROID_DOWNLOAD_LINK


def test_download_mobile_app_redirects_to_web_download_page_for_other_agents(settings):
    """Should redirect non-mobile user agents to the web download page."""
    settings.LOGIN_REDIRECT_URL = "https://dictaphone.example.com/"
    client = APIClient()

    res = client.get(
        "/api/v1.0/download-mobile-app/",
        HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)",
    )

    assert res.status_code == 302
    assert res["Location"] == urljoin(
        settings.LOGIN_REDIRECT_URL, "/download-mobile-app"
    )
