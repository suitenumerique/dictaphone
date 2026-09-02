"""Tests for admin classes."""

from io import BytesIO
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import default_storage
from django.test import override_settings
from django.urls import reverse

import pytest

from core import factories
from core.admin import (
    AiFileJobAdmin,
    FileAdmin,
    FileAdminForm,
    LatestTranscriptJobStatusFilter,
)
from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AiJobTypeChoices,
    File,
    FileAudioExtractionStateChoices,
)

pytestmark = pytest.mark.django_db


def test_file_admin_displays_latest_transcript_job_status():
    """File admin should display the status of the newest transcript job."""
    file = factories.FileFactory()
    factories.AiFileJobFactory(
        file=file,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
    )
    latest_transcript_job = factories.AiFileJobFactory(
        file=file,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
    )
    factories.AiFileJobFactory(
        file=file,
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.PENDING,
    )
    admin_instance = FileAdmin(File, Mock())

    annotated_file = admin_instance.get_queryset(Mock()).get(id=file.id)

    assert annotated_file.latest_transcript_job_status == AiJobStatusChoices.SUCCESS
    assert admin_instance.latest_transcript_job_status(annotated_file) == "Success"
    assert (
        annotated_file.latest_transcript_job_created_at
        == latest_transcript_job.created_at
    )
    assert (
        admin_instance.latest_transcript_job_created_at(annotated_file)
        == latest_transcript_job.created_at
    )


def test_file_admin_displays_new_storage_and_retention_fields_as_read_only():
    """New storage and retention fields should be visible but not editable."""
    admin_instance = FileAdmin(File, Mock())
    fields = {
        field
        for fieldset in admin_instance.fieldsets
        for field in fieldset[1]["fields"]
    }
    new_fields = {
        "storage_bucket_name",
        "original_file_data_delete_at",
        "original_file_data_delete_at_with_grace_period",
        "file_auto_hard_delete_at",
        "file_auto_hard_delete_at_with_grace_period",
        "trashbin_purge_at",
        "trashbin_purge_at_with_grace_period",
    }

    assert new_fields <= fields
    assert new_fields <= set(admin_instance.readonly_fields)


def test_file_admin_displays_creator_as_read_only():
    """Admins must not be able to change a file's owner."""
    admin_instance = FileAdmin(File, Mock())

    assert "creator" in admin_instance.readonly_fields


def test_file_admin_displays_audio_extraction_status():
    """File admin should display the localized audio extraction state."""
    file = factories.FileFactory(
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    admin_instance = FileAdmin(File, Mock())

    assert "audio_extraction_status" in admin_instance.list_display
    assert "audio_extraction_state" in admin_instance.list_filter
    assert "audio_extraction_state" not in admin_instance.readonly_fields
    assert admin_instance.audio_extraction_status(file) == "Audio extraction done"


def test_file_admin_can_only_reset_audio_extraction_to_pending():
    """Admins can reset extraction but cannot manually mark it successful."""
    pending = FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
    done = FileAudioExtractionStateChoices.EXTRACTION_DONE
    file = factories.FileFactory(audio_extraction_state=done)

    form = FileAdminForm(instance=file)
    assert [value for value, _ in form.fields["audio_extraction_state"].choices] == [
        done,
        pending,
    ]

    reset_form = FileAdminForm(
        data={**form.initial, "audio_extraction_state": pending},
        instance=file,
    )
    assert reset_form.is_valid()

    pending_file = factories.FileFactory(audio_extraction_state=pending)
    successful_form = FileAdminForm(
        data={"audio_extraction_state": done},
        instance=pending_file,
    )
    assert "audio_extraction_state" in successful_form.errors


@pytest.mark.parametrize(
    ("filter_value", "expected_file_index"),
    [
        (AiJobStatusChoices.SUCCESS, 0),
        (AiJobStatusChoices.FAILED, 1),
        ("none", 2),
    ],
)
def test_file_admin_filters_by_latest_transcript_job_status(
    filter_value, expected_file_index
):
    """The filter should use only the latest transcript job for each file."""
    files = [factories.FileFactory() for _ in range(3)]
    factories.AiFileJobFactory(
        file=files[0],
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
    )
    factories.AiFileJobFactory(
        file=files[0],
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
    )
    factories.AiFileJobFactory(
        file=files[1],
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.FAILED,
    )
    factories.AiFileJobFactory(
        file=files[2],
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.SUCCESS,
    )
    admin_instance = FileAdmin(File, Mock())
    status_filter = LatestTranscriptJobStatusFilter.__new__(
        LatestTranscriptJobStatusFilter
    )
    status_filter.value = Mock(return_value=filter_value)

    queryset = status_filter.queryset(Mock(), admin_instance.get_queryset(Mock()))

    assert list(queryset.values_list("id", flat=True)) == [
        files[expected_file_index].id
    ]


@patch("core.admin.call_transcribe_service.delay")
def test_admin_action_retry_transcript_generation_on_files(mock_delay):
    """Admin action should enqueue transcript retries for selected files."""
    file1 = factories.FileFactory()
    file2 = factories.FileFactory()

    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "en"}
    queryset = File.objects.filter(id__in=[file1.id, file2.id])

    admin_instance.retry_transcript_generation(request, queryset)

    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(file1.id, language="en")
    mock_delay.assert_any_call(file2.id, language="en")
    admin_instance.message_user.assert_called_once()


@patch("core.admin.call_transcribe_service.delay")
def test_admin_action_retry_transcript_generation_invalid_language(mock_delay):
    """Admin action should reject invalid language values."""
    file = factories.FileFactory()

    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "zzz"}
    queryset = File.objects.filter(id=file.id)

    admin_instance.retry_transcript_generation(request, queryset)

    mock_delay.assert_not_called()
    admin_instance.message_user.assert_called_once_with(
        request,
        "Invalid language selected.",
        level=messages.ERROR,
    )


@patch("core.admin.call_transcribe_service.delay")
def test_admin_action_retry_transcript_generation_with_latest_language(mock_delay):
    """Admin action should reuse each file's latest transcript job language."""
    file1 = factories.FileFactory()
    file2 = factories.FileFactory()
    file_without_transcript = factories.FileFactory()
    factories.AiFileJobFactory(
        file=file1,
        type=AiJobTypeChoices.TRANSCRIPT,
        language="en",
    )
    factories.AiFileJobFactory(
        file=file1,
        type=AiJobTypeChoices.TRANSCRIPT,
        language="fr",
    )
    factories.AiFileJobFactory(
        file=file2,
        type=AiJobTypeChoices.TRANSCRIPT,
        language="en",
    )
    factories.AiFileJobFactory(
        file=file2,
        type=AiJobTypeChoices.SUMMARIZE,
        language="fr",
    )

    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    queryset = File.objects.filter(
        id__in=[file1.id, file2.id, file_without_transcript.id]
    )

    admin_instance.retry_transcript_generation_with_latest_language(request, queryset)

    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(file1.id, language="fr")
    mock_delay.assert_any_call(file2.id, language="en")
    assert admin_instance.message_user.call_count == 2
    admin_instance.message_user.assert_any_call(
        request,
        "1 file(s) skipped because no transcript job was found.",
        level=messages.WARNING,
    )


def test_admin_ai_file_job_delete_model_removes_storage_file():
    """Single AI job deletion in admin should remove storage object."""
    ai_job = factories.AiFileJobFactory(type=AiJobTypeChoices.SUMMARIZE)
    default_storage.save(ai_job.key, BytesIO(b"summary"))

    admin_instance = AiFileJobAdmin(AiFileJob, Mock())

    assert default_storage.exists(ai_job.key)
    admin_instance.delete_model(request=Mock(), obj=ai_job)

    assert not AiFileJob.objects.filter(id=ai_job.id).exists()
    assert not default_storage.exists(ai_job.key)


@pytest.mark.django_db(transaction=True)
@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
def test_file_admin_bulk_delete_selected_files(client):
    """Bulk file deletion removes files and all their storage artifacts."""
    admin_user = factories.UserFactory(
        admin_email="admin@example.com",
        is_staff=True,
        is_superuser=True,
    )
    files = [
        factories.FileFactory(
            upload_bytes=b"content",
            audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
        )
        for _ in range(2)
    ]
    transcript_jobs = [
        factories.AiFileJobFactory(
            file=file,
            type=AiJobTypeChoices.TRANSCRIPT,
            status=AiJobStatusChoices.SUCCESS,
        )
        for file in files
    ]
    for job in transcript_jobs:
        default_storage.save(job.key, BytesIO(b'{"segments": []}'))

    selected_ids = [str(file.id) for file in files]
    changelist_url = reverse("admin:core_file_changelist")
    storage_keys = [
        key for file in files for key in (file.file_key, file.audio_file_key)
    ] + [job.key for job in transcript_jobs]

    assert all(default_storage.exists(key) for key in storage_keys)

    client.force_login(admin_user)
    response = client.post(
        changelist_url,
        data={
            "action": "delete_selected",
            "_selected_action": selected_ids,
            "index": 0,
        },
    )

    assert response.status_code == 200
    assert b"Delete multiple objects" in response.content

    response = client.post(
        changelist_url,
        data={
            "action": "delete_selected",
            "_selected_action": selected_ids,
            "post": "yes",
        },
    )

    assert response.status_code == 302
    assert not File.objects.filter(id__in=selected_ids).exists()
    assert not any(default_storage.exists(key) for key in storage_keys)


@pytest.mark.django_db(transaction=True)
def test_admin_ai_file_job_delete_queryset_removes_storage_files():
    """Bulk AI job deletion in admin should remove all storage objects."""
    ai_job_1 = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)
    ai_job_2 = factories.AiFileJobFactory(type=AiJobTypeChoices.SUMMARIZE)
    default_storage.save(ai_job_1.key, BytesIO(b'{"segments": []}'))
    default_storage.save(ai_job_2.key, BytesIO(b"summary"))

    admin_instance = AiFileJobAdmin(AiFileJob, Mock())
    queryset = AiFileJob.objects.filter(id__in=[ai_job_1.id, ai_job_2.id])

    assert default_storage.exists(ai_job_1.key)
    assert default_storage.exists(ai_job_2.key)
    admin_instance.delete_queryset(request=Mock(), queryset=queryset)

    assert not AiFileJob.objects.filter(id=ai_job_1.id).exists()
    assert not AiFileJob.objects.filter(id=ai_job_2.id).exists()
    assert not default_storage.exists(ai_job_1.key)
    assert not default_storage.exists(ai_job_2.key)
