"""Tests for frontend configuration endpoint."""

from django.test import Client


def test_frontend_configuration_contains_mobile_apps(settings):
    """Frontend configuration should expose mobile app version settings."""
    settings.MOBILE_APP_IOS_VERSION = "1.2.0"
    settings.MOBILE_APP_IOS_MIN_VERSION = "1.1.0"
    settings.MOBILE_APP_ANDROID_VERSION = "2.3.0"
    settings.MOBILE_APP_ANDROID_MIN_VERSION = "2.0.0"

    response = Client().get("/api/v1.0/config/")

    assert response.status_code == 200
    assert response.json()["mobile_app"] == {
        "ios_version": "1.2.0",
        "ios_min_version": "1.1.0",
        "android_version": "2.3.0",
        "android_min_version": "2.0.0",
        "android_download_link": "https://example.com/android-app-download-link",
        "ios_download_link": "https://example.com/ios-app-download-link",
    }
