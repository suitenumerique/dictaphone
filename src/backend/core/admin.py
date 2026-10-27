"""Admin classes and registrations for core app."""

import logging

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.auth import admin as auth_admin
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils.translation import gettext_lazy as _

from kombu.exceptions import KombuError

from core.authentication.mobile import revoke_session

from . import models
from .audio_jobs import start_audio_extraction
from .tasks.file import (
    TranscriptionAlreadyPending,
    call_transcribe_service,
    create_transcription_job,
    process_file_deletion,
)

logger = logging.getLogger(__name__)


def _publish_transcript_job(job_id):
    """Release an unsubmitted reservation if publishing fails."""
    try:
        call_transcribe_service.delay(job_id)
    except KombuError:
        with transaction.atomic():
            job = (
                models.AiFileJob.objects.select_for_update()
                .filter(
                    pk=job_id,
                    status=models.AiJobStatusChoices.PENDING,
                    remote_job_id__isnull=True,
                )
                .first()
            )
            if job:
                job.mark_failed()
        logger.exception("Publishing transcript job %s failed", job_id)


def hard_delete_file(file):
    """Hard delete a file, soft deleting it first when needed."""
    if file.deleted_at is None:
        file.soft_delete()
    file.hard_delete()
    process_file_deletion.delay(file.id)


@transaction.atomic
def _queue_transcript_job(file_id, language):
    """Reserve the input and publish the task after the job has committed."""
    job = create_transcription_job(file_id, language=language, allow_pending=False)
    transaction.on_commit(lambda: _publish_transcript_job(job.id))


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

    def has_add_permission(self, request, obj=None):
        """Prevent creating files through the user inline."""
        return False

    def get_queryset(self, request):
        """Hide hard deleted files in the inline."""
        return super().get_queryset(request).filter(hard_deleted_at__isnull=True)


class AiJobDurationMixin:
    """Display elapsed AI job time using the available lifecycle timestamps."""

    @admin.display(description=_("Computed duration (s)"))
    def computed_duration(self, obj):
        """Use the last update as the end time for a finished AI job."""
        if (
            obj.status
            not in {
                models.AiJobStatusChoices.SUCCESS,
                models.AiJobStatusChoices.FAILED,
            }
            or obj.created_at is None
            or obj.updated_at is None
        ):
            return None
        return round((obj.updated_at - obj.created_at).total_seconds(), 2)


class AudioJobDurationMixin:
    """Display elapsed audio worker time from its lifecycle timestamps."""

    @admin.display(description=_("Computed duration (s)"))
    def computed_duration(self, obj):
        """Compute worker duration when both start and completion are known."""
        if obj.started_at is None or obj.completed_at is None:
            return None
        return round((obj.completed_at - obj.started_at).total_seconds(), 2)


class AiFileJobInline(AiJobDurationMixin, admin.TabularInline):
    """Inline class for the AiFileJob model."""

    model = models.AiFileJob
    extra = 0
    fields = (
        "id",
        "remote_job_id",
        "type",
        "status",
        "failure_reason",
        "created_at",
        "computed_duration",
    )
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        """Prevent creating AI jobs through the file inline."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting AI jobs through the file inline."""
        return False

    def has_change_permission(self, request, obj=None):
        """Keep AI jobs viewable without allowing inline edits."""
        return False


class RetryTranscriptActionForm(ActionForm):
    """Admin action form used to choose the transcription language."""

    language = forms.ChoiceField(choices=models.ISO_639_1_CHOICES, required=False)


class AudioExtractionStatusFilter(admin.SimpleListFilter):
    """Filter files using the same inferred state as the public API."""

    title = _("audio extraction status")
    parameter_name = "audio_extraction_state"

    def lookups(self, request, model_admin):
        return models.FileAudioExtractionStateChoices.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(inferred_audio_state=self.value())
        return queryset


class AudioJobInline(AudioJobDurationMixin, admin.TabularInline):
    """Read-only attempt history on a file."""

    model = models.AudioJob
    extra = 0
    fields = (
        "id",
        "mode",
        "status",
        "attempt_number",
        "created_at",
        "started_at",
        "completed_at",
        "computed_duration",
    )
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


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

    inlines = (AiFileJobInline, AudioJobInline)
    action_form = RetryTranscriptActionForm
    actions = (
        "start_audio_extraction",
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
        AudioExtractionStatusFilter,
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
        "audio_extraction_state",
        "creator",
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

    def has_add_permission(self, request):
        """Prevent creating files through the admin."""
        return False

    def get_queryset(self, request):
        """Hide hard deleted files in admin listing and lookups."""
        latest_transcript_job = models.AiFileJob.objects.filter(
            file=OuterRef("pk"),
            type=models.AiJobTypeChoices.TRANSCRIPT,
        ).order_by("-created_at")
        return (
            super()
            .get_queryset(request)
            .with_audio_state()
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
        ordering="inferred_audio_state",
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

    def get_deleted_objects(self, objs, request):
        """File deletion owns job cleanup even when jobs cannot be deleted directly."""
        deleted, counts, permissions_needed, protected = super().get_deleted_objects(
            objs, request
        )
        permissions_needed.discard(models.AudioJob._meta.verbose_name)  # noqa: SLF001
        permissions_needed.discard(models.AiFileJob._meta.verbose_name)  # noqa: SLF001
        return deleted, counts, permissions_needed, protected

    def delete_queryset(self, request, queryset):
        """Hard delete all selected files."""
        for file in queryset:
            hard_delete_file(file)

    @admin.action(description=_("Start audio extraction"))
    def start_audio_extraction(self, request, queryset):
        """Start fresh work for eligible files without duplicating active attempts."""
        count = 0
        for file in queryset:
            try:
                start_audio_extraction(file.pk)
            except models.File.DoesNotExist:
                continue
            count += 1
        self.message_user(
            request,
            _("%(count)s file(s) queued for audio extraction.") % {"count": count},
        )

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

        enqueued_count = 0
        skipped_count = 0
        pending_count = 0
        for file in queryset:
            try:
                _queue_transcript_job(file.id, language)
            except TranscriptionAlreadyPending:
                pending_count += 1
                continue
            except ValueError, models.File.DoesNotExist:
                skipped_count += 1
                continue
            enqueued_count += 1

        self.message_user(
            request,
            _("%(count)s transcript retry job(s) enqueued.")
            % {"count": enqueued_count},
        )
        if skipped_count:
            self.message_user(
                request,
                _("%(count)s file(s) skipped because validated audio is unavailable.")
                % {"count": skipped_count},
                level=messages.WARNING,
            )
        self._report_pending_transcripts(request, pending_count)

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
        unavailable_count = 0
        pending_count = 0
        for file in files:
            if file.latest_transcript_job_language is None:
                skipped_count += 1
                continue
            try:
                _queue_transcript_job(file.id, file.latest_transcript_job_language)
            except TranscriptionAlreadyPending:
                pending_count += 1
                continue
            except ValueError, models.File.DoesNotExist:
                unavailable_count += 1
                continue
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
        if unavailable_count:
            self.message_user(
                request,
                _("%(count)s file(s) skipped because validated audio is unavailable.")
                % {"count": unavailable_count},
                level=messages.WARNING,
            )
        self._report_pending_transcripts(request, pending_count)

    def _report_pending_transcripts(self, request, count):
        """Report files skipped because another transcript is already pending."""
        if count:
            self.message_user(
                request,
                _(
                    "%(count)s file(s) skipped because a transcript job is already pending."
                )
                % {"count": count},
                level=messages.WARNING,
            )


@admin.register(models.AiFileJob)
class AiFileJobAdmin(AiJobDurationMixin, admin.ModelAdmin):
    """Admin class for the AiFileJob model."""

    list_display = (
        "id",
        "remote_job_id",
        "type",
        "status",
        "failure_reason",
        "language",
        "file",
        "created_at",
        "updated_at",
        "computed_duration",
    )
    list_filter = (
        "type",
        "status",
        "failure_reason",
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
    readonly_fields = (
        "id",
        "remote_job_id",
        "type",
        "status",
        "failure_reason",
        "file",
        "language",
        "docs_app_id",
        "docs_creation_in_progress",
        "validated_audio_job",
        "created_at",
        "updated_at",
        "computed_duration",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "remote_job_id",
                    "type",
                    "status",
                    "failure_reason",
                    "file",
                )
            },
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at", "computed_duration")},
        ),
    )

    def has_add_permission(self, request):
        """Prevent creating AI jobs through the admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting AI jobs through the admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Keep AI jobs viewable without allowing edits."""
        return False


class TranscriptionUsageAdminForm(forms.ModelForm):
    """Require an explanation for manual quota exemptions."""

    class Meta:
        model = models.TranscriptionUsage
        fields = ("ignored", "ignored_reason")

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("ignored") and not cleaned_data.get("ignored_reason"):
            self.add_error(
                "ignored_reason", _("Provide a reason for ignoring this usage.")
            )
        return cleaned_data


@admin.register(models.TranscriptionUsage)
class TranscriptionUsageAdmin(admin.ModelAdmin):
    """Inspect quota charges and edit only their exemption and explanation."""

    form = TranscriptionUsageAdminForm
    list_display = (
        "id",
        "user",
        "ai_job_id",
        "duration_seconds",
        "submitted_at",
        "ignored",
        "ignored_reason",
    )
    list_filter = ("ignored", "submitted_at")
    search_fields = ("id", "ai_job_id", "user__email")
    ordering = ("-submitted_at", "-id")
    readonly_fields = (
        "id",
        "user",
        "ai_job_id",
        "duration_seconds",
        "submitted_at",
        "created_at",
        "updated_at",
    )
    actions = None

    def has_add_permission(self, request):
        """Only transcription submission can create a charge."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Preserve the charge and its exemption history."""
        return False


@admin.register(models.AudioJob)
class AudioJobAdmin(AudioJobDurationMixin, admin.ModelAdmin):
    """Immutable attempt identity and lifecycle history; cleanup belongs to files."""

    list_display = (
        "id",
        "file",
        "mode",
        "status",
        "attempt_number",
        "created_at",
        "started_at",
        "completed_at",
        "computed_duration",
    )
    list_filter = ("mode", "status", "created_at", "started_at")
    search_fields = ("id", "file__id", "file__title", "extraction_id")
    ordering = ("-created_at", "-id")
    readonly_fields = (
        "id",
        "file",
        "mode",
        "status",
        "extraction_id",
        "attempt_number",
        "retry_of",
        "source_job",
        "output_key",
        "created_at",
        "updated_at",
        "started_at",
        "expires_at",
        "completed_at",
        "computed_duration",
        "duration_seconds",
        "error",
        "metadata",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.MobileAuthSession)
class MobileAuthSessionAdmin(admin.ModelAdmin):
    """Inspect and revoke mobile logins without exposing credentials."""

    list_display = (
        "id",
        "user",
        "created_at",
        "expires_at",
        "revoked_at",
        "revocation_reason",
    )
    list_filter = ("revocation_reason",)
    search_fields = ("user__email", "user__sub")
    fields = (
        "id",
        "user",
        "created_at",
        "expires_at",
        "revoked_at",
        "revocation_reason",
        "oidc_issuer",
        "oidc_sub",
        "oidc_sid",
    )
    readonly_fields = fields
    actions = ("revoke_selected_sessions", "revoke_all_sessions_for_users")

    def has_add_permission(self, request):
        """Sessions are created only by successful authentication."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Use revocation to retain an audit record and clear browser sessions."""
        return False

    @admin.action(description="Revoke selected mobile sessions")
    def revoke_selected_sessions(self, request, queryset):
        """Serialize administrative revocation against token rotation."""
        self._revoke(queryset)

    @admin.action(description="Revoke ALL mobile sessions for the selected users")
    def revoke_all_sessions_for_users(self, request, queryset):
        """Recover from a lost device or account compromise."""
        user_ids = list(queryset.values_list("user_id", flat=True))
        self._revoke(models.MobileAuthSession.objects.filter(user_id__in=user_ids))

    @staticmethod
    def _revoke(queryset):
        """All revocation paths take the same per-session row lock."""
        with transaction.atomic():
            for session in queryset.select_for_update().order_by("pk"):
                revoke_session(session, "admin")
