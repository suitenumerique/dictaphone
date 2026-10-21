"""Tests for the per-user audio upload limit exposed to the frontend."""

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from core import factories

pytestmark = pytest.mark.django_db


def test_upload_limit_requires_authentication():
    """Usage must not be exposed to anonymous requests."""
    response = APIClient().get("/api/v1.0/files/upload-limit/")
    assert response.status_code == 401


@pytest.mark.parametrize("restrictions_enabled", [True, False])
def test_upload_limit_matches_creation_rules(settings, restrictions_enabled):
    """Count analyzing/ready uploads, excluding pending, deleted and other users."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = restrictions_enabled
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "max_count_by_user": 2,
        },
    }
    user = factories.UserFactory()
    factories.FileFactory(creator=user, update_upload_state="pending")
    file = factories.FileFactory(creator=user, update_upload_state="ready")
    factories.FileFactory(creator=user, update_upload_state="analyzing")
    factories.FileFactory(
        creator=user, update_upload_state="ready", deleted_at=timezone.now()
    )
    factories.FileFactory()
    client = APIClient()
    client.force_login(user)

    # List filters must not change the count used for creation restrictions.
    response = client.get(
        "/api/v1.0/files/upload-limit/?upload_state=ready&is_deleted=true"
    )
    assert response.status_code == 200
    assert response.json() == {
        "count": 2,
        "limit": 2 if restrictions_enabled else None,
    }

    # The action recommended by the alert must immediately free a slot.
    file.soft_delete()
    response = client.get("/api/v1.0/files/upload-limit/")
    assert response.json()["count"] == 1
