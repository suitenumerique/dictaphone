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
from kombu.exceptions import OperationalError

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
    TranscriptionUsageAdmin,
)
from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AiJobTypeChoices,
    AudioJob,
    File,
    FileAudioExtractionStateChoices,
    TranscriptionUsage,
    User,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "password,error_code",
    [
        ("zQ7!vR2@kL9", "password_too_short"),
        ("password123456", "password_too_common"),
        ("739182645083", "password_entirely_numeric"),
        ("zQ7!vR2@kL9#", None),
    ],
)
@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
def test_user_admin_creation_validates_password(client, password, error_code):
    """The admin add view rejects weak passwords and accepts a strong 12-character one."""
    admin_user = factories.UserFactory(is_staff=True, is_superuser=True)
    client.force_login(admin_user)
    url = reverse("admin:core_user_add")
    response = client.get(url)
    assert response.status_code == 200

    data = {
        "password1": password,
        "password2": password,
        "usable_password": "true",
        "_save": "Save",
    }
    for inline in response.context["inline_admin_formsets"]:
        management_form = inline.formset.management_form
        data.update(
            {
                management_form.add_prefix(name): value
                for name, value in management_form.initial.items()
            }
        )

    user_count = User.objects.count()
    response = client.post(url, data)

    if error_code:
        assert response.status_code == 200
        errors = response.context["adminform"].form.errors.as_data()
        assert error_code in [error.code for error in errors["password2"]]
        assert User.objects.count() == user_count
    else:
        assert response.status_code == 302
        assert User.objects.count() == user_count + 1
        user = User.objects.exclude(pk=admin_user.pk).get()
        assert user.check_password(password)


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


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
def test_transcription_usage_admin_only_edits_ignore_fields(client):
    """Admins can exempt and reinstate usage without changing the original charge."""
    admin_user = factories.UserFactory(is_staff=True, is_superuser=True)
    usage = factories.TranscriptionUsageFactory()
    original = (
        usage.user_id,
        usage.ai_job_id,
        usage.duration_seconds,
        usage.submitted_at,
    )
    client.force_login(admin_user)
    request = Mock(user=admin_user)
    admin_instance = TranscriptionUsageAdmin(TranscriptionUsage, admin.site)
    assert set(admin_instance.get_form(request, usage).base_fields) == {
        "ignored",
        "ignored_reason",
    }
    assert not admin_instance.get_actions(request)
    url = reverse("admin:core_transcriptionusage_change", args=[usage.pk])
    assert client.get(url).status_code == 200
    assert (
        client.get(reverse("admin:core_transcriptionusage_changelist")).status_code
        == 200
    )

    response = client.post(
        url,
        {
            "ignored": "on",
            "ignored_reason": "Support adjustment",
            "duration_seconds": "0",
            "user": str(admin_user.pk),
            "ai_job_id": str(admin_user.pk),
        },
    )

    assert response.status_code == 302
    usage.refresh_from_db()
    assert usage.ignored is True
    assert usage.ignored_reason == "Support adjustment"
    assert (
        usage.user_id,
        usage.ai_job_id,
        usage.duration_seconds,
        usage.submitted_at,
    ) == original

    response = client.post(url, {"ignored_reason": "Reinstated after review"})
    assert response.status_code == 302
    usage.refresh_from_db()
    assert usage.ignored is False


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
def test_transcription_usage_admin_requires_ignore_reason(client):
    """An exemption must have an explanation in the admin."""
    client.force_login(factories.UserFactory(is_staff=True, is_superuser=True))
    usage = factories.TranscriptionUsageFactory()

    response = client.post(
        reverse("admin:core_transcriptionusage_change", args=[usage.pk]),
        {"ignored": "on", "ignored_reason": "   "},
    )

    assert response.status_code == 200
    assert "ignored_reason" in response.context["adminform"].form.errors
    usage.refresh_from_db()
    assert usage.ignored is False


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("action", ["add", "delete"])
def test_transcription_usage_admin_disallows_create_and_delete(client, method, action):
    """Even superusers cannot fabricate or delete quota history through the admin."""
    client.force_login(factories.UserFactory(is_staff=True, is_superuser=True))
    usage = factories.TranscriptionUsageFactory()
    url = reverse(
        f"admin:core_transcriptionusage_{action}",
        args=[usage.pk] if action == "delete" else None,
    )

    response = getattr(client, method)(url)

    assert response.status_code == 403
    assert TranscriptionUsage.objects.count() == 1


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
def test_admin_action_retry_transcript_generation_on_files(
    mock_delay, django_capture_on_commit_callbacks
):
    """Admin action should enqueue transcript retries for selected files."""
    file1 = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    file2 = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )

    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "en"}
    queryset = File.objects.filter(id__in=[file1.id, file2.id])

    with django_capture_on_commit_callbacks(execute=True):
        admin_instance.retry_transcript_generation(request, queryset)
        mock_delay.assert_not_called()

    assert mock_delay.call_count == 2
    for file in (file1, file2):
        job = file.ai_jobs.get()
        assert job.language == "en"
        assert job.status == AiJobStatusChoices.PENDING
        assert job.validated_audio_job_id == file.latest_audio_job.id
        mock_delay.assert_any_call(job.id)
    admin_instance.message_user.assert_called_once()


@patch("core.admin.call_transcribe_service.delay")
def test_admin_action_retry_skips_files_without_validated_audio(mock_delay):
    """An unavailable audio input cannot leave an unsubmitted pending job."""
    file = factories.FileFactory()
    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "en"}

    admin_instance.retry_transcript_generation(request, File.objects.filter(pk=file.pk))

    mock_delay.assert_not_called()
    assert not file.ai_jobs.exists()
    admin_instance.message_user.assert_any_call(
        request,
        "1 file(s) skipped because validated audio is unavailable.",
        level=messages.WARNING,
    )


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
def test_admin_action_retry_transcript_generation_with_latest_language(
    mock_delay, django_capture_on_commit_callbacks
):
    """Admin action should reuse each file's latest transcript job language."""
    file1 = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    file2 = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    file_without_transcript = factories.FileFactory()
    factories.AiFileJobFactory(
        file=file1,
        type=AiJobTypeChoices.TRANSCRIPT,
        language="en",
        status=AiJobStatusChoices.SUCCESS,
    )
    factories.AiFileJobFactory(
        file=file1,
        type=AiJobTypeChoices.TRANSCRIPT,
        language="fr",
        status=AiJobStatusChoices.SUCCESS,
    )
    factories.AiFileJobFactory(
        file=file2,
        type=AiJobTypeChoices.TRANSCRIPT,
        language="en",
        status=AiJobStatusChoices.SUCCESS,
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

    with django_capture_on_commit_callbacks(execute=True):
        admin_instance.retry_transcript_generation_with_latest_language(
            request, queryset
        )

    assert mock_delay.call_count == 2
    for file, language in ((file1, "fr"), (file2, "en")):
        job = file.ai_jobs.latest("created_at")
        assert job.language == language
        assert job.validated_audio_job_id == file.latest_audio_job.id
        mock_delay.assert_any_call(job.id)
    assert admin_instance.message_user.call_count == 2
    admin_instance.message_user.assert_any_call(
        request,
        "1 file(s) skipped because no transcript job was found.",
        level=messages.WARNING,
    )


@pytest.mark.parametrize(
    "action",
    ["retry_transcript_generation", "retry_transcript_generation_with_latest_language"],
)
@patch("core.admin.call_transcribe_service.delay")
def test_admin_retry_skips_pending_transcript(mock_delay, action):
    """Neither admin retry action may reserve a duplicate pending transcript."""
    file = factories.FileFactory(
        upload_bytes=b"audio",
        audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = factories.AiFileJobFactory(
        file=file,
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
        remote_job_id=None,
    )
    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "en"}

    getattr(admin_instance, action)(request, File.objects.filter(pk=file.pk))

    mock_delay.assert_not_called()
    assert list(file.ai_jobs.all()) == [job]
    admin_instance.message_user.assert_any_call(
        request,
        "0 transcript retry job(s) enqueued.",
    )
    admin_instance.message_user.assert_any_call(
        request,
        "1 file(s) skipped because a transcript job is already pending.",
        level=messages.WARNING,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "action",
    ["retry_transcript_generation", "retry_transcript_generation_with_latest_language"],
)
@patch("core.admin.call_transcribe_service.delay")
def test_admin_retry_recovers_publish_failure_and_continues(mock_delay, action):
    """A failed publication frees the reservation and does not abort the batch."""
    files = [
        factories.FileFactory(
            upload_bytes=b"audio",
            audio_extraction_state=FileAudioExtractionStateChoices.EXTRACTION_DONE,
        )
        for _ in range(2)
    ]
    for file in files:
        factories.AiFileJobFactory(
            file=file,
            type=AiJobTypeChoices.TRANSCRIPT,
            status=AiJobStatusChoices.FAILED,
        )
    mock_delay.side_effect = [OperationalError("broker unavailable"), None]
    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "en"}
    queryset = File.objects.filter(pk__in=[file.pk for file in files]).order_by("pk")

    getattr(admin_instance, action)(request, queryset)

    assert mock_delay.call_count == 2
    failed_job = AiFileJob.objects.get(pk=mock_delay.call_args_list[0].args[0])
    queued_job = AiFileJob.objects.get(pk=mock_delay.call_args_list[1].args[0])
    assert failed_job.status == AiJobStatusChoices.FAILED
    assert failed_job.remote_job_id is None
    assert queued_job.status == AiJobStatusChoices.PENDING
    assert all(file.ai_jobs.count() == 2 for file in files)


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
