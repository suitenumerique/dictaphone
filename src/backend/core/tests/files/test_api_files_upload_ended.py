"""Test related to file upload ended API."""

import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.db import connections
from django.utils import timezone

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from core import factories, models
from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AiJobTypeChoices,
    FileTypeChoices,
    FileUploadStateChoices,
)

pytestmark = pytest.mark.django_db


def test_api_file_upload_ended_anonymous():
    """Anonymous users should not be allowed to end an upload."""
    file = factories.FileFactory()
    response = APIClient().post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 401


def test_api_file_upload_ended_non_creator_not_found():
    """Users without write permissions should not be allowed to end an upload."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory()

    response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 404


def test_api_file_upload_ended_on_wrong_upload_state():
    """
    Users should not be allowed to end an upload on files that are not in the PENDING upload state.
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING,
        creator=user,
        update_upload_state=FileUploadStateChoices.READY,
    )

    response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 400
    assert response.json() == {
        "file": "This action is only available for files in PENDING state."
    }


@pytest.mark.django_db(transaction=True)
@patch("core.api.viewsets.start_audio_extraction")
def test_api_file_upload_ended_success(mock_queue, settings):
    """
    Users should be able to end an upload on files that are files and in the UPLOADING upload state.
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "allowed_mimetypes": ["text/html", "text/plain"],
        },
    }
    bucket_configurations = {
        name: dict(configuration)
        for name, configuration in settings.S3_BUCKET_CONFIGURATIONS.items()
    }
    default_bucket_configuration = bucket_configurations["default"]
    default_bucket_configuration.pop("domain_replace", None)
    settings.S3_BUCKET_CONFIGURATIONS = bucket_configurations

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING,
        filename="my_file.txt",
        mimetype="text/html",
        creator=user,
    )

    default_storage.save(
        file.temporary_file_key,
        BytesIO(b"my prose"),
    )
    assert not AiFileJob.objects.filter(
        file=file, type=AiJobTypeChoices.TRANSCRIPT, status=AiJobStatusChoices.PENDING
    ).exists()

    now = timezone.now()
    with freeze_time(now):
        response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 200

    file.refresh_from_db()
    assert file.upload_state == FileUploadStateChoices.READY
    assert file.mimetype == "text/plain"
    assert file.size == 8

    assert response.json()["mimetype"] == "text/plain"

    mock_queue.assert_called_once_with(file.id)

    assert not AiFileJob.objects.filter(
        file=file, type=AiJobTypeChoices.TRANSCRIPT
    ).exists()


@pytest.mark.django_db(transaction=True)
@patch("core.api.viewsets.start_audio_extraction")
def test_api_file_upload_ended_uses_file_language_for_transcription(
    mock_queue, settings
):
    """Upload-ended should call transcription service with file configured language."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False

    create_response = client.post(
        "/api/v1.0/files/",
        {
            "title": "my file",
            "filename": "my_file.m4a",
            "duration_seconds": 1,
            "type": FileTypeChoices.AUDIO_RECORDING,
            "language": "en",
        },
        format="json",
    )
    assert create_response.status_code == 201, create_response.json()
    file_id = create_response.json()["id"]

    file = models.File.objects.get(id=file_id)
    assert file.language == "en"

    default_storage.save(file.temporary_file_key, BytesIO(b"my prose"))

    response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")
    assert response.status_code == 200
    mock_queue.assert_called_once_with(file.id)


@pytest.mark.django_db(transaction=True)
def test_api_file_upload_ended_mimetype_not_allowed(settings, caplog):
    """
    Test that the API returns a 400 when the mimetype is not allowed.
    File should be deleted and the file should be deleted from the storage.
    """
    settings.RESTRICT_UPLOAD_FILE_TYPE = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "allowed_mimetypes": ["application/pdf"],
        }
    }

    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING, filename="my_file.txt", creator=user
    )

    default_storage.save(
        file.temporary_file_key,
        BytesIO(b"my prose"),
    )

    with caplog.at_level(logging.WARNING):
        response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 400
    assert (
        f"upload_ended: mimetype not allowed text/plain for file {file.file_key}"
        in caplog.text
    )

    assert not models.File.objects.filter(id=file.id).exists()
    assert not default_storage.exists(file.file_key)


@patch("core.api.viewsets.start_audio_extraction")
def test_api_file_upload_ended_mimetype_not_allowed_not_checking_mimetype(
    mock_post, settings
):
    """
    Test that the API returns a 200 when the mimetype is not allowed but not checking the mimetype.
    """
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "allowed_mimetypes": ["application/pdf"],
        }
    }
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING, filename="my_file.txt", creator=user
    )

    default_storage.save(
        file.temporary_file_key,
        BytesIO(b"my prose"),
    )

    response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 200
    mock_post.assert_called_once_with(file.id)

    file.refresh_from_db()
    assert file.upload_state == FileUploadStateChoices.READY
    assert file.mimetype == "text/plain"
    assert file.size == 8

    assert response.json()["mimetype"] == "text/plain"


@patch(
    "core.api.viewsets.utils.detect_mimetype", return_value="audio/webm; codecs=opus"
)
@patch("core.api.viewsets.start_audio_extraction")
def test_api_file_upload_ended_allows_mimetype_with_spaces_in_parameters(
    mock_post, mock_detect_mimetype, settings
):
    """
    MIME type parameters may contain spaces even when the allow list does not.
    """
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "allowed_mimetypes": ["audio/webm;codecs=opus"],
        }
    }

    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING,
        filename="my_file.webm",
        creator=user,
    )

    default_storage.save(
        file.temporary_file_key,
        BytesIO(b"fake webm content"),
    )

    response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 200
    mock_post.assert_called_once_with(file.id)
    assert mock_detect_mimetype.call_count == 1

    file.refresh_from_db()
    assert file.upload_state == FileUploadStateChoices.READY
    assert file.mimetype == "audio/webm; codecs=opus"
    assert file.size == 17

    assert response.json()["mimetype"] == "audio/webm; codecs=opus"


@patch("core.api.viewsets.start_audio_extraction")
def test_api_upload_ended_mismatch_mimetype_with_object_storage(
    mock_post, settings, caplog
):
    """
    Object on storage should have the same mimetype than the one saved in the
    File object.
    """
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "allowed_mimetypes": ["text/html", "application/pdf"],
        }
    }

    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING,
        filename="my_file.pdf",
        title="my_file.pdf",
        creator=user,
    )

    s3_client = default_storage.connection.meta.client

    s3_client.put_object(
        Bucket=default_storage.bucket_name,
        Key=file.temporary_file_key,
        ContentType="text/html",
        Body=BytesIO(
            b'<meta http-equiv="refresh" content="0; url=https://fichiers.numerique.gouv.fr">'
        ),
        Metadata={
            "foo": "bar",
        },
    )

    head_object = s3_client.head_object(
        Bucket=default_storage.bucket_name, Key=file.temporary_file_key
    )

    assert head_object["ContentType"] == "text/html"
    with caplog.at_level(logging.INFO, logger="core.api.viewsets"):
        response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")
    assert (
        "upload_ended: content type mismatch between object storage and file,"
        " updating from text/html to application/pdf" in caplog.text
    )
    assert response.status_code == 200
    mock_post.assert_called_once_with(file.id)

    file.refresh_from_db()

    assert file.mimetype == "application/pdf"

    head_object = s3_client.head_object(
        Bucket=default_storage.bucket_name, Key=file.file_key
    )
    assert head_object["ContentType"] == "application/pdf"
    assert head_object["Metadata"] == {"foo": "bar"}


@pytest.mark.parametrize("declared_content_type", ["audio/mp4", "audio/x-m4a"])
@patch("core.api.viewsets.utils.detect_mimetype", return_value="video/mp4")
@patch("core.api.viewsets.start_audio_extraction")
def test_api_upload_ended_keeps_declared_mp4_audio_mimetype(
    mock_post, mock_detect_mimetype, settings, caplog, declared_content_type
):
    """
    When libmagic reports video/mp4 for an m4a-like file, the API should keep
    the declared audio content type from object storage.
    """
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "allowed_mimetypes": ["audio/mp4", "audio/x-m4a"],
        }
    }

    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING,
        filename="my_file.m4a",
        creator=user,
    )

    s3_client = default_storage.connection.meta.client
    s3_client.put_object(
        Bucket=default_storage.bucket_name,
        Key=file.temporary_file_key,
        ContentType=declared_content_type,
        Body=BytesIO(b"fake m4a content"),
        Metadata={"foo": "bar"},
    )

    with caplog.at_level(logging.INFO, logger="core.api.viewsets"):
        response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")

    assert response.status_code == 200
    mock_post.assert_called_once_with(file.id)
    assert mock_detect_mimetype.call_count == 1
    assert (
        f"upload_ended: detected mimetype for file {file.file_key} is video/mp4 "
        f"but it was declared as {declared_content_type}, leaving it that way."
        in caplog.text
    )
    assert (
        "upload_ended: content type mismatch between object storage and file"
        not in caplog.text
    )

    file.refresh_from_db()
    assert file.mimetype == declared_content_type
    assert response.json()["mimetype"] == declared_content_type

    head_object = s3_client.head_object(
        Bucket=default_storage.bucket_name, Key=file.file_key
    )
    assert head_object["ContentType"] == declared_content_type
    assert head_object["Metadata"] == {"foo": "bar"}


@pytest.mark.django_db(transaction=True)
def test_api_upload_ended_file_size_exceeded(settings, caplog):
    """
    Test when the file size exceeds the allowed max upload file size
    should return a 400 and delete the file.
    """

    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "max_size": 0,
        }
    }

    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING, filename="my_file.txt", creator=user
    )

    default_storage.save(
        file.temporary_file_key,
        BytesIO(b"my prose"),
    )

    with caplog.at_level(logging.INFO, logger="core.api.viewsets"):
        response = client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")
    assert (
        f"upload_ended: file size (8) for file {file.file_key} higher than the allowed max size"
        in caplog.text
    )
    assert response.status_code == 400

    assert not models.File.objects.filter(id=file.id).exists()
    assert not default_storage.exists(file.file_key)


@pytest.mark.django_db(transaction=True)
def test_api_file_upload_ended_concurrent_calls_are_serialized(settings):
    """Only one concurrent upload-ended call can finalize a pending upload."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "allowed_mimetypes": ["text/plain"],
        },
    }

    user = factories.UserFactory()
    file = factories.FileFactory(
        type=FileTypeChoices.AUDIO_RECORDING,
        filename="my_file.txt",
        creator=user,
    )
    default_storage.save(file.temporary_file_key, BytesIO(b"my prose"))

    def call_upload_ended():
        try:
            client = APIClient()
            client.force_login(user)
            return client.post(f"/api/v1.0/files/{file.id!s}/upload-ended/")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(call_upload_ended),
            executor.submit(call_upload_ended),
        ]
        responses = [future.result() for future in futures]

    status_codes = sorted(response.status_code for response in responses)
    assert status_codes == [200, 400]

    failed_response = next(
        response for response in responses if response.status_code == 400
    )
    assert failed_response.json() == {
        "file": "This action is only available for files in PENDING state."
    }

    file.refresh_from_db()
    assert file.upload_state == FileUploadStateChoices.READY


@patch("core.api.viewsets.start_audio_extraction")
def test_upload_ended_rechecks_file_count_and_allows_retry(mock_queue, settings):
    """Pending uploads share no slots until finalized, and deletion frees a slot."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "max_count_by_user": 1,
            "allowed_mimetypes": ["text/plain"],
        },
    }
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)
    files = factories.FileFactory.create_batch(2, creator=user, filename="audio.txt")
    factories.FileFactory(
        creator=user, update_upload_state="ready", deleted_at=timezone.now()
    )
    factories.FileFactory(update_upload_state="ready")
    for file in files:
        default_storage.save(file.temporary_file_key, BytesIO(b"my prose"))

    response = client.post(f"/api/v1.0/files/{files[0].pk}/upload-ended/")
    assert response.status_code == 200
    response = client.post(f"/api/v1.0/files/{files[1].pk}/upload-ended/")
    assert response.status_code == 403
    assert response.json() == {
        "detail": "You have reached the maximum number of files for this type."
    }
    files[1].refresh_from_db()
    assert files[1].upload_state == FileUploadStateChoices.PENDING
    assert mock_queue.call_count == 1

    files[0].soft_delete()
    response = client.post(f"/api/v1.0/files/{files[1].pk}/upload-ended/")
    assert response.status_code == 200
    assert mock_queue.call_count == 2


@pytest.mark.django_db(transaction=True)
@patch("core.api.viewsets.start_audio_extraction")
def test_upload_ended_concurrent_files_respect_count_limit(mock_queue, settings):
    """Concurrent finalizations for one creator cannot both reserve the last slot."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = True
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "max_count_by_user": 1,
            "allowed_mimetypes": ["text/plain"],
        },
    }
    user = factories.UserFactory()
    files = factories.FileFactory.create_batch(2, creator=user, filename="audio.txt")
    for file in files:
        default_storage.save(file.temporary_file_key, BytesIO(b"my prose"))

    def finalize(file):
        try:
            client = APIClient()
            client.force_login(user)
            return client.post(f"/api/v1.0/files/{file.pk}/upload-ended/").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(finalize, files)) == [200, 403]

    assert (
        models.File.objects.filter(
            creator=user, upload_state=FileUploadStateChoices.PENDING
        ).count()
        == 1
    )
    mock_queue.assert_called_once()


@patch("core.api.viewsets.start_audio_extraction")
def test_upload_ended_ignores_count_when_restrictions_disabled(mock_queue, settings):
    """Disabling upload restrictions also disables the finalization count check."""
    settings.FILE_UPLOAD_APPLY_RESTRICTIONS = False
    settings.FILE_UPLOAD_RESTRICTIONS = {
        "audio_recording": {
            **settings.FILE_UPLOAD_RESTRICTIONS["audio_recording"],
            "max_count_by_user": 0,
        },
    }
    user = factories.UserFactory()
    file = factories.FileFactory(creator=user, filename="audio.txt")
    default_storage.save(file.temporary_file_key, BytesIO(b"my prose"))
    client = APIClient()
    client.force_login(user)

    response = client.post(f"/api/v1.0/files/{file.pk}/upload-ended/")
    assert response.status_code == 200
    mock_queue.assert_called_once_with(file.pk)
