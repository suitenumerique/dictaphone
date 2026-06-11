"""Admin classes and registrations for core app."""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.auth import admin as auth_admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from . import models
from .tasks.file import call_transcribe_service, process_file_deletion
from .utils import generate_download_file_url


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

    inlines = (AiFileJobInline,)
    action_form = RetryTranscriptActionForm
    actions = ("retry_transcript_generation",)

    list_display = (
        "id",
        "title",
        "type",
        "creator",
        "upload_state",
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
        "preview_url",
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
            _("Derived info"),
            {
                "fields": (
                    "is_ready",
                    "extension",
                    "key_base",
                    "file_key",
                    "preview_url",
                )
            },
        ),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    def preview_url(self, obj):
        """Return a clickable preview URL for the file."""
        if not obj.is_ready:
            return "-"
        url = generate_download_file_url(obj, expires_in=60 * 60)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">Open File</a>', url
        )

    def get_queryset(self, request):
        """Hide hard deleted files in admin listing and lookups."""
        return super().get_queryset(request).filter(hard_deleted_at__isnull=True)

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
