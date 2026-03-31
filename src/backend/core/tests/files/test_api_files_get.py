"""
Tests for files API endpoint in dictaphone's core app: get
"""

import pytest
from faker import Faker
from rest_framework.test import APIClient

from core import factories, models

fake = Faker()
pytestmark = pytest.mark.django_db


def test_api_files_get_anonymous_not_allowed():
    """
    Anonymous users should not be allowed to retrieve a file.
    """
    file_obj = factories.FileFactory(type=models.FileTypeChoices.AUDIO_RECORDING)

    response = APIClient().get(f"/api/v1.0/files/{file_obj.id}/")

    assert response.status_code == 401


def test_api_files_get_not_found():
    """
    Retrieving a missing file should return 404.
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    response = client.get("/api/v1.0/files/00000000-0000-0000-0000-000000000000/")

    assert response.status_code == 404


def test_api_files_get_authentificated_user_allowed():
    """
    Authenticated users should be allowed to retrieve their file.
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file_obj = factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        creator=user,
        title="item 1",
    )

    response = client.get(f"/api/v1.0/files/{file_obj.id}/")

    assert response.status_code == 200


def test_api_files_get_format():
    """Validate the format of a file as returned by the retrieve view."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file_obj = factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        title="item 1",
        creator=user,
    )

    response = client.get(f"/api/v1.0/files/{file_obj.id}/")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(file_obj.id),
        "created_at": file_obj.created_at.isoformat().replace("+00:00", "Z"),
        "creator": {
            "id": str(file_obj.creator.id),
            "full_name": file_obj.creator.full_name,
            "short_name": file_obj.creator.short_name,
        },
        "ai_jobs": [],
        "title": file_obj.title,
        "updated_at": file_obj.updated_at.isoformat().replace("+00:00", "Z"),
        "type": models.FileTypeChoices.AUDIO_RECORDING,
        "upload_state": file_obj.upload_state,
        "url": None,
        "mimetype": file_obj.mimetype,
        "filename": file_obj.filename,
        "duration_seconds": file_obj.duration_seconds,
        "size": None,
        "description": None,
        "deleted_at": None,
        "hard_deleted_at": None,
        "abilities": {
            "destroy": True,
            "hard_delete": False,
            "media_auth": True,
            "partial_update": True,
            "restore": False,
            "retrieve": True,
            "update": True,
            "upload_ended": True,
        },
    }


def test_api_files_get_authentificated_non_creator_not_allowed():
    """
    Authenticated users shouldn't be allowed to retrieve a file they do not own.
    """
    creator = factories.UserFactory()
    other_user = factories.UserFactory()
    client = APIClient()

    file_obj = factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        creator=creator,
        title="item 1",
    )

    client.force_login(creator)
    response = client.get(f"/api/v1.0/files/{file_obj.id}/")
    assert response.status_code == 200

    client.force_login(other_user)
    response = client.get(f"/api/v1.0/files/{file_obj.id}/")
    assert response.status_code == 404
