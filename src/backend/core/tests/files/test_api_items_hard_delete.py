"""Test the file hard delete endpoint."""

import pytest
from rest_framework.test import APIClient

from core import factories, models

pytestmark = pytest.mark.django_db


def test_api_files_hard_delete_anonymous():
    """
    Anonymous users should not be allowed to hard delete a file.
    """
    file = factories.FileFactory()
    response = APIClient().delete(f"/api/v1.0/files/{file.id!s}/hard-delete/")
    assert response.status_code == 401


def test_api_files_hard_delete_authenticated_not_owner():
    """
    Authenticated users should not be allowed to hard delete a file if they are not the owner.
    """
    user = factories.UserFactory()
    file = factories.FileFactory()
    file.soft_delete()

    client = APIClient()
    client.force_login(user)

    response = client.delete(f"/api/v1.0/files/{file.id!s}/hard-delete/")
    assert response.status_code == 404


def test_api_files_hard_delete_authenticated_owner():
    """
    Authenticated users should be allowed to hard delete a file if they are the owner.
    """
    user = factories.UserFactory()
    file = factories.FileFactory(creator=user)
    file.soft_delete()

    client = APIClient()
    client.force_login(user)

    response = client.delete(f"/api/v1.0/files/{file.id!s}/hard-delete/")
    assert response.status_code == 204

    assert not models.File.objects.filter(id=file.id).exists()


def test_api_files_hard_delete_authenticated_owner_not_soft_deleted_should_fails():
    """
    Authenticated users should not be allowed to hard delete a file if it is not soft deleted.
    """
    user = factories.UserFactory()
    file = factories.FileFactory(creator=user)

    client = APIClient()
    client.force_login(user)

    response = client.delete(f"/api/v1.0/files/{file.id!s}/hard-delete/")
    assert response.status_code == 403


def test_api_files_hard_delete_authenticated_owner_already_hard_deleted_should_fail():
    """
    Authenticated users should not be allowed to hard delete a file if it is already hard deleted.
    """
    user = factories.UserFactory()
    file = factories.FileFactory()
    file.soft_delete()
    file.hard_delete()

    client = APIClient()
    client.force_login(user)

    response = client.delete(f"/api/v1.0/files/{file.id!s}/hard-delete/")
    assert response.status_code == 404


#
#
# def test_api_files_hard_delete_suspicious_item_should_not_work_for_non_creator():
#     """
#     Non-creators should not be able to hard delete suspicious files.
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
#     response = client.delete(f"/api/v1.0/files/{suspicious_file.id!s}/hard-delete/")
#     assert response.status_code == 404
#
#
# def test_api_files_hard_delete_suspicious_item_should_work_for_creator():
#     """
#     Creators should be able to hard delete their own suspicious files.
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
#     response = client.delete(f"/api/v1.0/files/{suspicious_file.id!s}/hard-delete/")
#     assert response.status_code == 204
#
#     assert not models.File.objects.filter(id=suspicious_file.id).exists()
