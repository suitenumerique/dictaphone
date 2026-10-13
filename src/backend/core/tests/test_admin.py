"""Tests for admin classes."""

from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib import admin, messages
from django.core.files.storage import default_storage
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

import pytest

from core import factories
from core.admin import (
    AiFileJobAdmin,
    AiFileJobInline,
    AudioExtractionStatusFilter,
    AudioJobAdmin,
    AudioJobInline,
    FileAdmin,
    FileInline,
    LatestTranscriptJobStatusFilter,
)
from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AiJobTypeChoices,
    AudioJob,
    File,
    FileAudioExtractionStateChoices,
    User,
)

pytestmark = pytest.mark.django_db


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
def test_ai_job_admin_is_view_only(client):
    """Superusers can inspect AI jobs but cannot submit edits."""
    admin_user = factories.UserFactory(is_staff=True, is_superuser=True)
    job = factories.AiFileJobFactory(status=AiJobStatusChoices.PENDING)
    client.force_login(admin_user)
    url = reverse("admin:core_aifilejob_change", args=[job.pk])

    response = client.get(url)

    assert response.status_code == 200
    assert b'name="status"' not in response.content
    assert b'name="_save"' not in response.content

    response = client.post(url, {"status": AiJobStatusChoices.SUCCESS})

    assert response.status_code == 403
    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.PENDING


def test_ai_job_inline_has_no_editable_fields():
    """The file inline must expose only read-only AI job information."""
    admin_instance = AiFileJobInline(File, admin.site)
    request = Mock()
    request.user = factories.UserFactory(is_staff=True, is_superuser=True)

    formset = admin_instance.get_formset(request)

    assert not formset.form.base_fields
    assert admin_instance.has_change_permission(request) is False


@pytest.mark.parametrize("admin_class", [AiFileJobAdmin, AiFileJobInline])
@pytest.mark.parametrize(
    ("status", "expected_duration"),
    [
        (AiJobStatusChoices.SUCCESS, 65.25),
        (AiJobStatusChoices.FAILED, 65.25),
        (AiJobStatusChoices.PENDING, None),
    ],
)
def test_ai_job_admin_computed_duration(admin_class, status, expected_duration):
    """AI job timing is only available once the job has finished."""
    created_at = timezone.now()
    job = AiFileJob(
        status=status,
        created_at=created_at,
        updated_at=created_at + timedelta(seconds=65.25),
    )
    admin_instance = admin_class(AiFileJob, Mock())

    assert admin_instance.computed_duration(job) == expected_duration


@pytest.mark.parametrize("admin_class", [AudioJobAdmin, AudioJobInline])
@pytest.mark.parametrize(
    ("has_started", "has_completed", "expected_duration"),
    [(True, True, 65.25), (True, False, None), (False, False, None)],
)
def test_audio_job_admin_computed_duration(
    admin_class, has_started, has_completed, expected_duration
):
    """Audio worker duration excludes queue time and differs from media duration."""
    started_at = timezone.now()
    job = AudioJob(
        created_at=started_at - timedelta(minutes=5),
        started_at=started_at if has_started else None,
        completed_at=started_at + timedelta(seconds=65.25) if has_completed else None,
        duration_seconds=3600,
    )
    admin_instance = admin_class(AudioJob, Mock())

    assert admin_instance.computed_duration(job) == expected_duration


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
    assert AudioExtractionStatusFilter in admin_instance.list_filter
    assert "audio_extraction_state" in admin_instance.readonly_fields
    assert admin_instance.audio_extraction_status(file) == "Audio extraction done"


def test_file_admin_starts_new_extraction_and_preserves_history():
    """Admin resets create a new attempt; historical results remain inspectable."""
    file = factories.FileFactory(
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE
    )
    admin_instance = FileAdmin(File, Mock())
    with patch.object(admin_instance, "message_user"):
        admin_instance.start_audio_extraction(Mock(), File.objects.filter(pk=file.pk))
        admin_instance.start_audio_extraction(Mock(), File.objects.filter(pk=file.pk))
    assert file.audio_jobs.count() == 3
    assert (
        file.audio_extraction_state
        == FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
    )


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


@pytest.mark.parametrize("model_name", ["file", "aifilejob"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_admin_cannot_add_files_or_ai_jobs(client, model_name, method):
    """Even superusers cannot create files or AI jobs through admin endpoints."""
    admin_user = factories.UserFactory(is_staff=True, is_superuser=True)
    client.force_login(admin_user)

    response = getattr(client, method)(reverse(f"admin:core_{model_name}_add"))

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("inline_class", "parent_model"),
    [(FileInline, User), (AiFileJobInline, File)],
)
def test_admin_cannot_add_files_or_ai_jobs_inline(inline_class, parent_model):
    """Inline forms must reject creation as well as standalone admin forms."""
    admin_instance = inline_class(parent_model, Mock())

    assert admin_instance.has_add_permission(Mock()) is False


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


@pytest.mark.parametrize("method", ["get", "post"])
def test_admin_cannot_delete_ai_job(client, method):
    """Even superusers cannot delete an AI job through its admin endpoint."""
    admin_user = factories.UserFactory(is_staff=True, is_superuser=True)
    ai_job = factories.AiFileJobFactory()
    client.force_login(admin_user)

    response = getattr(client, method)(
        reverse("admin:core_aifilejob_delete", args=[ai_job.pk]),
        data={"post": "yes"},
    )

    assert response.status_code == 403
    assert AiFileJob.objects.filter(pk=ai_job.pk).exists()


def test_admin_ai_file_job_has_no_bulk_delete_action():
    """The bulk delete action must be unavailable for AI jobs."""
    admin_instance = AiFileJobAdmin(AiFileJob, admin.site)
    request = Mock()
    request.GET = {}

    assert "delete_selected" not in admin_instance.get_actions(request)


def test_admin_cannot_delete_ai_jobs_inline():
    """AI job inline forms must reject deletion."""
    admin_instance = AiFileJobInline(File, Mock())

    assert admin_instance.has_delete_permission(Mock()) is False
