"""Admin classes and registrations for core app."""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.auth import admin as auth_admin
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.utils.translation import gettext_lazy as _

from . import models
from .tasks.file import call_transcribe_service, process_file_deletion


def hard_delete_file(file):
    """Hard delete a file, soft deleting it first when needed."""
    if file.deleted_at is None:
        file.soft_delete()
    file.hard_delete()
    process_file_deletion.delay(file.id)


class FileInlineFormSet(forms.BaseInlineFormSet):
    """Inline formset overriding delete behavior for files."""

    def delete_existing(self, obj, commit=True):
        """Hard delete files instead of calling model.delete()."""
        hard_delete_file(obj)


class FileInline(admin.TabularInline):
    """Inline class for the File model."""

    model = models.File
    formset = FileInlineFormSet
    fk_name = "creator"
    extra = 0
    fields = ("id", "title", "type", "upload_state", "created_at")
    readonly_fields = ("id", "created_at", "upload_state", "type")
    show_change_link = True

    def get_queryset(self, request):
        """Hide hard deleted files in the inline."""
        return super().get_queryset(request).filter(hard_deleted_at__isnull=True)


class AiFileJobInline(admin.TabularInline):
    """Inline class for the AiFileJob model."""

    model = models.AiFileJob
    extra = 0
    fields = ("id", "remote_job_id", "type", "status", "created_at")
    readonly_fields = ("id", "created_at")
    show_change_link = True


class RetryTranscriptActionForm(ActionForm):
    """Admin action form used to choose the transcription language."""

    language = forms.ChoiceField(choices=models.ISO_639_1_CHOICES, required=True)


class FileAdminForm(forms.ModelForm):
    """Allow admins to reset extraction without manually completing it."""

    class Meta:
        model = models.File
        fields = (
            "type",
            "title",
            "creator",
            "deleted_at",
            "hard_deleted_at",
            "filename",
            "duration_seconds",
            "upload_state",
            "audio_extraction_state",
            "lifecycle_state",
            "mimetype",
            "size",
            "language",
            "description",
            "malware_detection_info",
            "source",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pending_state = models.FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
        current_state = self.instance.audio_extraction_state
        state_labels = dict(models.FileAudioExtractionStateChoices.choices)
        choices = [(current_state, state_labels[current_state])]
        if current_state != pending_state:
            choices.append((pending_state, state_labels[pending_state]))
        self.fields["audio_extraction_state"].choices = choices

    def clean_audio_extraction_state(self):
        """Reject manually setting extraction to any non-pending state."""
        state = self.cleaned_data["audio_extraction_state"]
        current_state = self.instance.audio_extraction_state
        pending_state = models.FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION
        if state not in {current_state, pending_state}:
            raise ValidationError(
                _("Audio extraction can only be reset to pending by an admin.")
            )
        return state


class LatestTranscriptJobStatusFilter(admin.SimpleListFilter):
    """Filter files by the status of their latest transcript job."""

    title = _("latest transcript job status")
    parameter_name = "latest_transcript_job_status"

    def lookups(self, request, model_admin):
        """Return transcript statuses and an option for files without a job."""
        return (*models.AiJobStatusChoices.choices, ("none", _("No transcript job")))

    def queryset(self, request, queryset):
        """Filter using the latest transcript status annotation from FileAdmin."""
        if self.value() == "none":
            return queryset.filter(latest_transcript_job_status__isnull=True)
        if self.value() in models.AiJobStatusChoices.values:
            return queryset.filter(latest_transcript_job_status=self.value())
        return queryset


@admin.register(models.User)
class UserAdmin(auth_admin.UserAdmin):
    """Admin class for the User model"""

    inlines = (FileInline,)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "admin_email",
                    "password",
                )
            },
        ),
        (
            _("Personal info"),
            {
                "fields": (
                    "sub",
                    "email",
                    "full_name",
                    "short_name",
                    "language",
                    "timezone",
                    "flag_show_mobile_app_popup",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_device",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    list_display = (
        "id",
        "sub",
        "admin_email",
        "email",
        "full_name",
        "short_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "is_device",
        "created_at",
        "updated_at",
        "flag_show_mobile_app_popup",
    )
    list_filter = ("is_staff", "is_superuser", "is_device", "is_active")
    ordering = (
        "is_active",
        "-is_superuser",
        "-is_staff",
        "-is_device",
        "-updated_at",
        "full_name",
    )
    readonly_fields = (
        "id",
        "sub",
        "email",
        "full_name",
        "short_name",
        "created_at",
        "updated_at",
    )
    search_fields = ("id", "sub", "admin_email", "email", "full_name")


@admin.register(models.File)
class FileAdmin(admin.ModelAdmin):
    """Admin class for the File model."""

    form = FileAdminForm
    inlines = (AiFileJobInline,)
    action_form = RetryTranscriptActionForm
    actions = (
        "retry_transcript_generation",
        "retry_transcript_generation_with_latest_language",
    )

    list_display = (
        "id",
        "title",
        "type",
        "creator",
        "upload_state",
        "audio_extraction_status",
        "latest_transcript_job_status",
        "latest_transcript_job_created_at",
        "deleted_at",
        "hard_deleted_at",
        "created_at",
        "updated_at",
        "duration_seconds",
        "source",
        "language",
        "lifecycle_state",
    )
    list_filter = (
        "type",
        "upload_state",
        "audio_extraction_state",
        LatestTranscriptJobStatusFilter,
        "lifecycle_state",
        "created_at",
        "updated_at",
        "deleted_at",
        "hard_deleted_at",
    )
    search_fields = (
        "id",
        "title",
        "filename",
        "mimetype",
        "description",
        "creator__email",
        "creator__admin_email",
        "creator__full_name",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "hard_deleted_at",
        "description",
        "malware_detection_info",
        "is_ready",
        "extension",
        "key_base",
        "file_key",
        "upload_state",
        "source",
        "language",
        "lifecycle_state",
        "duration_seconds",
        "type",
        "mimetype",
        "size",
        "storage_bucket_name",
        "original_file_data_delete_at",
        "original_file_data_delete_at_with_grace_period",
        "file_auto_hard_delete_at",
        "file_auto_hard_delete_at_with_grace_period",
        "trashbin_purge_at",
        "trashbin_purge_at_with_grace_period",
    )
    autocomplete_fields = ("creator",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "title",
                    "type",
                    "creator",
                    "filename",
                    "language",
                    "upload_state",
                    "audio_extraction_state",
                    "source",
                    "lifecycle_state",
                )
            },
        ),
        (
            _("Content"),
            {
                "fields": (
                    "mimetype",
                    "size",
                    "duration_seconds",
                    "description",
                    "malware_detection_info",
                )
            },
        ),
        (
            _("Deletion"),
            {
                "fields": (
                    "deleted_at",
                    "hard_deleted_at",
                )
            },
        ),
        (
            _("Storage and retention"),
            {
                "fields": (
                    "storage_bucket_name",
                    "original_file_data_delete_at",
                    "original_file_data_delete_at_with_grace_period",
                    "file_auto_hard_delete_at",
                    "file_auto_hard_delete_at_with_grace_period",
                    "trashbin_purge_at",
                    "trashbin_purge_at_with_grace_period",
                )
            },
        ),
        (
            _("Derived info"),
            {
                "fields": (
                    "is_ready",
                    "extension",
                    "key_base",
                    "file_key",
                )
            },
        ),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        """Hide hard deleted files in admin listing and lookups."""
        latest_transcript_job = models.AiFileJob.objects.filter(
            file=OuterRef("pk"),
            type=models.AiJobTypeChoices.TRANSCRIPT,
        ).order_by("-created_at")
        return (
            super()
            .get_queryset(request)
            .filter(hard_deleted_at__isnull=True)
            .annotate(
                latest_transcript_job_status=Subquery(
                    latest_transcript_job.values("status")[:1]
                ),
                latest_transcript_job_created_at=Subquery(
                    latest_transcript_job.values("created_at")[:1]
                ),
            )
        )

    @admin.display(
        description=_("Latest transcript job status"),
        ordering="latest_transcript_job_status",
    )
    def latest_transcript_job_status(self, obj):
        """Display the localized status of the latest transcript job."""
        status_labels = dict(models.AiJobStatusChoices.choices)
        return status_labels.get(obj.latest_transcript_job_status, "-")

    @admin.display(
        description=_("Audio extraction status"),
        ordering="audio_extraction_state",
    )
    def audio_extraction_status(self, obj):
        """Display the localized audio extraction state."""
        return obj.get_audio_extraction_state_display()

    @admin.display(
        description=_("Latest transcript job created on"),
        ordering="latest_transcript_job_created_at",
    )
    def latest_transcript_job_created_at(self, obj):
        """Display when the latest transcript job was created."""
        return obj.latest_transcript_job_created_at or "-"

    def delete_model(self, request, obj):
        """Hard delete instead of calling model.delete()."""
        hard_delete_file(obj)

    def delete_queryset(self, request, queryset):
        """Hard delete all selected files."""
        for file in queryset:
            hard_delete_file(file)

    @admin.action(description=_("Retry transcript generation"))
    def retry_transcript_generation(self, request, queryset):
        """Retry transcript generation for selected files."""
        language = request.POST.get("language")
        valid_languages = {code for code, _ in models.ISO_639_1_CHOICES}
        if language not in valid_languages:
            self.message_user(
                request,
                _("Invalid language selected."),
                level=messages.ERROR,
            )
            return

        for file in queryset:
            call_transcribe_service.delay(file.id, language=language)

        self.message_user(
            request,
            _("%(count)s transcript retry job(s) enqueued.")
            % {"count": queryset.count()},
        )

    @admin.action(description=_("Retry transcript generation with latest job language"))
    def retry_transcript_generation_with_latest_language(self, request, queryset):
        """Retry transcripts using each file's latest transcript job language."""
        latest_transcript_job = models.AiFileJob.objects.filter(
            file=OuterRef("pk"),
            type=models.AiJobTypeChoices.TRANSCRIPT,
        ).order_by("-created_at")
        files = queryset.annotate(
            latest_transcript_job_language=Subquery(
                latest_transcript_job.values("language")[:1]
            )
        )

        enqueued_count = 0
        skipped_count = 0
        for file in files:
            if file.latest_transcript_job_language is None:
                skipped_count += 1
                continue
            call_transcribe_service.delay(
                file.id,
                language=file.latest_transcript_job_language,
            )
            enqueued_count += 1

        self.message_user(
            request,
            _("%(count)s transcript retry job(s) enqueued.")
            % {"count": enqueued_count},
        )
        if skipped_count:
            self.message_user(
                request,
                _("%(count)s file(s) skipped because no transcript job was found.")
                % {"count": skipped_count},
                level=messages.WARNING,
            )


@admin.register(models.AiFileJob)
class AiFileJobAdmin(admin.ModelAdmin):
    """Admin class for the AiFileJob model."""

    list_display = (
        "id",
        "remote_job_id",
        "type",
        "status",
        "language",
        "file",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "type",
        "status",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "id",
        "remote_job_id",
        "file__id",
        "file__title",
        "file__filename",
    )
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("file",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "remote_job_id",
                    "type",
                    "status",
                    "file",
                )
            },
        ),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    def delete_model(self, request, obj):
        """Delete the AI job and its storage artifact."""
        obj.delete()

    def delete_queryset(self, request, queryset):
        """Delete selected AI jobs with per-object cleanup."""
        for ai_job in queryset.iterator():
            ai_job.delete()
