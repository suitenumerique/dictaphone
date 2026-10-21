"""Tests for the per-user audio upload limit exposed to the frontend."""

from datetime import timedelta

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from core import factories, models

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


@pytest.mark.parametrize(
    "hidden_fields",
    [
        {"hard_deleted_at": timezone.now()},
        {"lifecycle_state": "pending_auto_hard_delete"},
        {"file_auto_hard_delete_at": timezone.now() - timedelta(days=1)},
    ],
)
def test_upload_limit_excludes_files_hidden_by_retention(settings, hidden_fields):
    """Hidden files must not occupy slots that the user cannot free."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "max_count_by_user": 2,
        },
    }
    user = factories.UserFactory()
    visible = factories.FileFactory(creator=user, update_upload_state="ready")
    hidden = factories.FileFactory(creator=user, update_upload_state="ready")
    models.File.objects.filter(pk=hidden.pk).update(**hidden_fields)
    client = APIClient()
    client.force_login(user)

    response = client.get("/api/v1.0/files/?upload_state=ready&is_deleted=false")
    assert response.status_code == 200
    assert [file["id"] for file in response.json()["results"]] == [str(visible.pk)]

    response = client.get("/api/v1.0/files/upload-limit/")
    assert response.status_code == 200
    assert response.json() == {"count": 1, "limit": 2}

    response = client.post(
        "/api/v1.0/files/",
        {
            "type": "audio_recording",
            "filename": "new.mp3",
            "title": "New",
            "duration_seconds": 1,
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
