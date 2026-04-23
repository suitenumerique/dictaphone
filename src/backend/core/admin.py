"""Admin classes and registrations for core app."""

from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from . import models
from .utils import generate_download_file_url


class FileInline(admin.TabularInline):
    """Inline class for the File model."""

    model = models.File
    fk_name = "creator"
    extra = 0
    fields = ("id", "title", "type", "upload_state", "created_at")
    readonly_fields = ("id", "created_at")
    show_change_link = True


class AiFileJobInline(admin.TabularInline):
    """Inline class for the AiFileJob model."""

    model = models.AiFileJob
    extra = 0
    fields = ("id", "remote_job_id", "type", "status", "created_at")
    readonly_fields = ("id", "created_at")
    show_change_link = True


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
    )
    list_filter = (
        "type",
        "upload_state",
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
        "is_pending_upload",
        "preview_url",
        "extension",
        "key_base",
        "file_key",
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
                    "upload_state",
                )
            },
        ),
        (
            _("Content"),
            {
                "fields": (
                    "mimetype",
                    "size",
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
                    "is_pending_upload",
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
        if obj.is_pending_upload:
            return "-"
        url = generate_download_file_url(obj, expires_in=60 * 60)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">Open File</a>', url
        )


@admin.register(models.AiFileJob)
class AiFileJobAdmin(admin.ModelAdmin):
    """Admin class for the AiFileJob model."""

    list_display = (
        "id",
        "remote_job_id",
        "type",
        "status",
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
