"""
Tests for files API endpoint in dictaphone's core app: list
"""

from datetime import timedelta
from unittest import mock

from django.utils import timezone

import pytest
from faker import Faker
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core import factories, models

fake = Faker()
pytestmark = pytest.mark.django_db


def test_api_files_list_anonymous_not_allowed():
    """
    Anonymous users should not be allowed to list files whatever the
    """
    response = APIClient().get("/api/v1.0/files/")
    assert response.status_code == 401


def test_api_files_list_authentificated_user_allowed():
    """
    Authentificated users should be allowed to list files
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    response = client.get("/api/v1.0/files/")
    assert response.status_code == 200
    assert response.data == {"count": 0, "next": None, "previous": None, "results": []}


def test_api_files_list_authentificated_user_allowed_with_jwt():
    """Authenticated users should be allowed to list files with JWT auth."""
    user = factories.UserFactory()
    access = RefreshToken.for_user(user).access_token

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = client.get("/api/v1.0/files/")
    assert response.status_code == 200
    assert response.data == {"count": 0, "next": None, "previous": None, "results": []}


def test_api_files_list_format(settings):
    """Validate the format of files as returned by the list view."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        title="item 1",
        creator=user,
    )

    # A file from another user should not appear
    factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        title="file 2",
    )

    # hard deleted file should not appear
    factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        hard_deleted_at=timezone.now(),
        title="hard deleted item",
        creator=user,
    )

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    content = response.json()
    results = content.pop("results")
    assert content == {
        "count": 1,
        "next": None,
        "previous": None,
    }
    assert len(results) == 1
    assert results == [
        {
            "id": str(file.id),
            "created_at": file.created_at.isoformat().replace("+00:00", "Z"),
            "creator": {
                "id": str(file.creator.id),
                "full_name": file.creator.full_name,
                "short_name": file.creator.short_name,
            },
            "ai_jobs": [],
            "title": file.title,
            "updated_at": file.updated_at.isoformat().replace("+00:00", "Z"),
            "type": models.FileTypeChoices.AUDIO_RECORDING,
            "upload_state": file.upload_state,
            "lifecycle_state": file.lifecycle_state,
            "url": None,
            "mimetype": file.mimetype,
            "filename": file.filename,
            "duration_seconds": file.duration_seconds,
            "size": None,
            "source": "unknown",
            "language": file.language,
            "description": None,
            "deleted_at": None,
            "hard_deleted_at": None,
            "original_file_file_delete_at": (
                file.created_at
                + timedelta(days=settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS)
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "will_auto_delete_at": (
                file.created_at
                + timedelta(days=settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS)
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "abilities": {
                "destroy": True,
                "hard_delete": False,
                "media_auth": True,
                "restore": False,
                "partial_update": True,
                "retrieve": True,
                "update": True,
                "upload_ended": True,
            },
        }
    ]


def test_api_files_list_excludes_files_past_hard_delete_deadline(settings):
    """Files older than hard-delete deadline should be excluded from API list."""
    settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS = 10
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    visible_file = factories.FileFactory(creator=user)
    excluded_file = factories.FileFactory(creator=user)
    models.File.objects.filter(pk=excluded_file.pk).update(
        created_at=timezone.now() - timedelta(days=11),
    )

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    returned_ids = {result["id"] for result in response.json()["results"]}
    assert str(visible_file.id) in returned_ids
    assert str(excluded_file.id) not in returned_ids


def test_api_files_list_excludes_pending_auto_hard_delete_files():
    """Files pending auto hard delete should not be listed."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    visible_file = factories.FileFactory(creator=user)
    excluded_file = factories.FileFactory(creator=user)
    excluded_file.lifecycle_state = (
        models.FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE
    )
    excluded_file.save(update_fields=["lifecycle_state"])

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    returned_ids = {result["id"] for result in response.json()["results"]}
    assert str(visible_file.id) in returned_ids
    assert str(excluded_file.id) not in returned_ids


def test_api_files_list_has_url_for_ready_active_file(settings):
    """Ready active files newer than original-data cutoff should expose media URL."""
    settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS = 10
    user = factories.UserFactory()
    file = factories.FileFactory(creator=user)
    file.upload_state = models.FileUploadStateChoices.READY
    file.save(update_fields=["upload_state"])

    client = APIClient()
    client.force_login(user)

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["id"] == str(file.id)
    assert result["url"] is not None


@mock.patch.object(PageNumberPagination, "get_page_size", return_value=2)
def test_api_files_list_pagination(
    _mock_page_size,
):
    """Pagination should work as expected."""
    user = factories.UserFactory()

    client = APIClient()
    client.force_login(user)

    file_ids = [
        str(file.id)
        for file in factories.FileFactory.create_batch(
            3,
            creator=user,
            type=models.FileTypeChoices.AUDIO_RECORDING,
        )
    ]
    # Get page 1
    response = client.get(
        "/api/v1.0/files/",
    )

    assert response.status_code == 200
    content = response.json()

    assert content["count"] == 3
    assert content["next"] == "http://testserver/api/v1.0/files/?page=2"
    assert content["previous"] is None

    assert len(content["results"]) == 2
    for file in content["results"]:
        file_ids.remove(file["id"])

    # Get page 2
    response = client.get(
        "/api/v1.0/files/?page=2",
    )

    assert response.status_code == 200
    content = response.json()

    assert content["count"] == 3
    assert content["next"] is None
    assert content["previous"] == "http://testserver/api/v1.0/files/"

    assert len(content["results"]) == 1
    for file in content["results"]:
        file_ids.remove(file["id"])
    assert file_ids == []
