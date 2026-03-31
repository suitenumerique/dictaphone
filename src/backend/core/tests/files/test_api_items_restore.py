"""
Test restoring files after a soft delete via the detail action API endpoint.
"""

from datetime import timedelta

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from core import factories

pytestmark = pytest.mark.django_db


def test_api_files_restore_anonymous_user():
    """Anonymous users should not be able to restore deleted files."""
    now = timezone.now() - timedelta(days=15)
    file = factories.FileFactory(deleted_at=now)

    response = APIClient().post(f"/api/v1.0/files/{file.id!s}/restore/")

    assert response.status_code == 401


def test_api_files_restore_authenticated_no_permission():
    """
    Authenticated users who are not owners of a deleted file should
    not be allowed to restore it.
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    now = timezone.now() - timedelta(days=15)
    file = factories.FileFactory(deleted_at=now)

    response = client.post(f"/api/v1.0/files/{file.id!s}/restore/")

    assert response.status_code == 404
    assert response.json() == {"detail": "No File matches the given query."}

    file.refresh_from_db()
    assert file.deleted_at == now


def test_api_files_restore_authenticated_owner_success():
    """The owner of a deleted file should be able to restore it."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    now = timezone.now() - timedelta(days=15)
    file = factories.FileFactory(deleted_at=now, creator=user)

    response = client.post(f"/api/v1.0/files/{file.id!s}/restore/")

    assert response.status_code == 200
    assert response.json() == {"detail": "file has been successfully restored."}

    file.refresh_from_db()
    assert file.deleted_at is None


def test_api_files_restore_authenticated_owner_not_deleted():
    """An error should be raised when trying to restore a file that is not deleted."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(creator=user)

    response = client.post(f"/api/v1.0/files/{file.id!s}/restore/")

    assert response.status_code == 403

    file.refresh_from_db()
    assert file.deleted_at is None


def test_api_files_restore_authenticated_owner_expired():
    """It should not be possible to restore a file beyond the allowed time limit."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    now = timezone.now() - timedelta(days=40)
    file = factories.FileFactory(creator=user, deleted_at=now)

    response = client.post(f"/api/v1.0/files/{file.id!s}/restore/")

    assert response.status_code == 400
    assert response.json() == {
        "deleted_at": ["This item was permanently deleted and cannot be restored."]
    }


#
# def test_api_files_restore_suspicious_item_should_not_work_for_non_creator():
#     """
#     Non-creators should not be able to restore suspicious files.
#     """
#     creator = factories.UserFactory()
#     other_user = factories.UserFactory()
#     client = APIClient()
#     client.force_login(other_user)
#
#     suspicious_file = factories.FileFactory(
#         creator=creator,
#         update_upload_state=models.FileUploadStateChoices.SUSPICIOUS,
#         users=[
#             (creator, models.RoleChoices.OWNER),
#             (other_user, models.RoleChoices.ADMIN),
#         ],
#         type=models.FileTypeChoices.FILE,
#         filename="suspicious.txt",
#     )
#     suspicious_file.soft_delete()
#
#     response = client.post(f"/api/v1.0/files/{suspicious_file.id!s}/restore/")
#     assert response.status_code == 404
#
#
# def test_api_files_restore_suspicious_item_should_work_for_creator():
#     """
#     Creators should be able to restore their own suspicious files.
#     """
#     creator = factories.UserFactory()
#     client = APIClient()
#     client.force_login(creator)
#
#     suspicious_file = factories.FileFactory(
#         creator=creator,
#         update_upload_state=models.FileUploadStateChoices.SUSPICIOUS,
#         users=[(creator, models.RoleChoices.OWNER)],
#         type=models.FileTypeChoices.FILE,
#         filename="suspicious.txt",
#     )
#     suspicious_file.soft_delete()
#
#     response = client.post(f"/api/v1.0/files/{suspicious_file.id!s}/restore/")
#     assert response.status_code == 200
#     assert response.json() == {"detail": "file has been successfully restored."}
#
#     # Verify that the file has been restored
#     suspicious_file.refresh_from_db()
#     assert suspicious_file.deleted_at is None
