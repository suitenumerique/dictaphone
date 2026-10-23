"""
Tests for files API endpoint in dictaphone's core app: get
"""

from datetime import timedelta

from django.utils import timezone

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


def test_api_files_get_format(settings):
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
        "lifecycle_state": file_obj.lifecycle_state,
        "url": None,
        "playback_url": None,
        "mimetype": file_obj.mimetype,
        "filename": file_obj.filename,
        "duration_seconds": file_obj.duration_seconds,
        "size": None,
        "audio_extraction_state": file_obj.audio_extraction_state,
        "source": "unknown",
        "language": file_obj.language,
        "description": None,
        "deleted_at": None,
        "hard_deleted_at": None,
        "original_file_file_delete_at": (
            file_obj.created_at
            + timedelta(days=settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS)
        )
        .isoformat()
        .replace("+00:00", "Z"),
        "will_auto_delete_at": (
            file_obj.created_at
            + timedelta(days=settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS)
        )
        .isoformat()
        .replace("+00:00", "Z"),
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


@pytest.mark.parametrize("endpoint", ["detail", "list"])
@pytest.mark.parametrize("status", [None, *models.AudioJobStatusChoices.values])
@pytest.mark.parametrize("legacy", [False, True])
def test_api_files_playback_prefers_completed_transcode(
    settings, endpoint, status, legacy
):
    """Playback uses completed audio while downloads always retain the original."""
    file = factories.FileFactory(
        update_upload_state=models.FileUploadStateChoices.READY,
    )
    job = None
    if status:
        job = models.AudioJob.objects.create(
            file=file,
            mode=models.AudioJobModeChoices.TRANSCODING,
            status=status,
            output_key=file.legacy_audio_file_key if legacy else None,
        )
        if status == models.AudioJobStatusChoices.SUCCESS:
            # A newer in-progress validation or retranscode must not hide available audio.
            models.AudioJob.objects.create(
                file=file,
                mode=models.AudioJobModeChoices.VALIDATION,
                source_job=job,
            )
            models.AudioJob.objects.create(
                file=file, mode=models.AudioJobModeChoices.TRANSCODING
            )
    client = APIClient()
    client.force_login(file.creator)
    path = f"/api/v1.0/files/{file.id}/" if endpoint == "detail" else "/api/v1.0/files/"
    response = client.get(path)
    assert response.status_code == 200
    data = response.data if endpoint == "detail" else response.data["results"][0]
    prefix = (
        f"{settings.MEDIA_BASE_URL}{settings.MEDIA_URL}"
        f"{file.configuration.storage_bucket_name}/"
    )
    assert data["url"] == f"{prefix}{file.file_key}"
    expected_key = (
        job.output_key
        if status == models.AudioJobStatusChoices.SUCCESS
        else file.file_key
    )
    assert data["playback_url"] == f"{prefix}{expected_key}"


@pytest.mark.parametrize("unavailable", ["pending", "expired", "deleted"])
def test_api_files_playback_respects_audio_availability(unavailable):
    """Completed transcodes must remain hidden when original audio access expires."""
    file = factories.FileFactory(
        update_upload_state=models.FileUploadStateChoices.READY,
    )
    models.AudioJob.objects.create(
        file=file,
        mode=models.AudioJobModeChoices.TRANSCODING,
        status=models.AudioJobStatusChoices.SUCCESS,
    )
    if unavailable == "pending":
        file.upload_state = models.FileUploadStateChoices.PENDING
    elif unavailable == "expired":
        file.original_file_data_delete_at = timezone.now() - timedelta(seconds=1)
    else:
        file.lifecycle_state = models.FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
    file.save()
    client = APIClient()
    client.force_login(file.creator)
    response = client.get(f"/api/v1.0/files/{file.id}/")
    assert response.status_code == 200
    assert response.data["url"] is None
    assert response.data["playback_url"] is None
