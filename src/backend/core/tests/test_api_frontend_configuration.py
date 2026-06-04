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


def test_frontend_configuration_exposes_base_settings(settings):
    """Frontend configuration should include base app settings and frontend overrides."""
    settings.LANGUAGE_CODE = "fr-fr"
    settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS = 365
    settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS = 31
    settings.DOCS_INTEGRATION_ENABLED = True
    settings.FRONTEND_CONFIGURATION = {"feature_flags": {"new_editor": True}}

    response = Client().get("/api/v1.0/config/")

    assert response.status_code == 200
    content = response.json()
    assert content["LANGUAGE_CODE"] == "fr-fr"
    assert content["data_policy"] == {
        "file_auto_hard_delete_after_days": 365,
        "original_file_data_delete_after_days": 31,
    }
    assert content["docs_integration_enabled"] is True
    assert content["feature_flags"] == {"new_editor": True}
