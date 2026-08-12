"""
Declare and configure the models for the Dictaphone core application
# pylint: disable=too-many-lines
"""

# pylint: disable=too-many-lines
import uuid
from logging import getLogger
from os.path import splitext
from typing import List

from django.conf import settings
from django.contrib.auth import models as auth_models
from django.contrib.auth.base_user import AbstractBaseUser
from django.core import mail, validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from timezone_field import TimeZoneField

from core.configuration import (
    get_profile_for_email,
    get_profile_for_file,
)
from core.enums import ISO_639_1_CHOICES
from core.storage import get_storage_for_file
from core.utils import format_transcript_for_markdown
from core.webhook_models import WhisperXResponse

logger = getLogger(__name__)


def get_trashbin_cutoff(file: File):
    """Return the absolute purge deadline for a soft-deleted file."""
    return file.configuration.trashbin_purge_at


def get_original_file_data_cutoff_datetime(
    file: File, *, include_grace_period: bool = False
):
    """Return cutoff datetime for original file data availability."""
    if include_grace_period:
        return file.configuration.original_file_data_delete_at_with_grace_period
    return file.configuration.original_file_data_delete_at


class BaseModel(models.Model):
    """
    Serves as an abstract base model for other models, ensuring that records are validated
    before saving as Django doesn't do it by default.

    Includes fields common to all models: a UUID primary key and creation/update timestamps.
    """

    id = models.UUIDField(
        verbose_name=_("id"),
        help_text=_("primary key for the record as UUID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(
        verbose_name=_("created on"),
        help_text=_("date and time at which a record was created"),
        auto_now_add=True,
        editable=False,
    )
    updated_at = models.DateTimeField(
        verbose_name=_("updated on"),
        help_text=_("date and time at which a record was last updated"),
        auto_now=True,
        editable=False,
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Call `full_clean` before saving."""
        self.full_clean()
        super().save(*args, **kwargs)


class User(AbstractBaseUser, BaseModel, auth_models.PermissionsMixin):
    """User model to work with OIDC only authentication."""

    sub_validator = validators.RegexValidator(
        regex=r"^[\w.@+-]+\Z",
        message=_(
            "Enter a valid sub. This value may contain only letters, "
            "numbers, and @/./+/-/_ characters."
        ),
    )

    sub = models.CharField(
        _("sub"),
        help_text=_(
            "Optional for pending users; required upon account activation. "
            "255 characters or fewer. Letters, numbers, and @/./+/-/_ characters only."
        ),
        max_length=255,
        unique=True,
        validators=[sub_validator],
        blank=True,
        null=True,
    )
    email = models.EmailField(_("identity email address"), blank=True, null=True)

    # Unlike the "email" field which stores the email coming from the OIDC token, this field
    # stores the email used by staff users to log in to the admin site
    admin_email = models.EmailField(
        _("admin email address"), unique=True, blank=True, null=True
    )
    full_name = models.CharField(_("full name"), max_length=100, null=True, blank=True)
    short_name = models.CharField(
        _("short name"), max_length=100, null=True, blank=True
    )
    language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        verbose_name=_("language"),
        help_text=_("The language in which the user wants to see the interface."),
    )
    timezone = TimeZoneField(
        choices_display="WITH_GMT_OFFSET",
        use_pytz=False,
        default=settings.TIME_ZONE,
        help_text=_("The timezone in which the user wants to see times."),
    )
    is_device = models.BooleanField(
        _("device"),
        default=False,
        help_text=_("Whether the user is a device or a real user."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    flag_show_mobile_app_popup = models.BooleanField(
        _("show mobile app popup"),
        default=True,
        help_text=_("Whether to show the mobile app popup to the user."),
    )

    objects = auth_models.UserManager()

    USERNAME_FIELD = "admin_email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "dictaphone_user"
        ordering = ("-created_at",)
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.email or self.admin_email or str(self.id)

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Email this user."""
        if not self.email:
            raise ValueError("User has no email address.")
        mail.send_mail(subject, message, from_email, [self.email], **kwargs)

    def get_teams(self):
        """
        Get list of teams in which the user is, as a list of strings.
        Must be cached if retrieved remotely.
        """
        return []


def get_resource_roles(resource: models.Model, user: User) -> List[str]:
    """
    Get all roles assigned to a user for a specific resource, including team-based roles.

    Args:
        resource: The resource to check permissions for
        user: The user to get roles for

    Returns:
        List of role strings assigned to the user
    """
    if not user.is_authenticated:
        return []

    # Use pre-annotated roles if available from viewset optimization
    if hasattr(resource, "user_roles"):
        return resource.user_roles or []

    try:
        return list(
            resource.accesses.filter_user(user)
            .values_list("role", flat=True)
            .distinct()
        )
    except IndexError, models.ObjectDoesNotExist:
        return []


class FileUploadStateChoices(models.TextChoices):
    """Possible states of a file."""

    PENDING = "pending", _("Pending")
    ANALYZING = "analyzing", _("Analyzing")
    # Commented out for now, as we may need this when we implement the malware detection logic.
    # SUSPICIOUS = "suspicious", _("Suspicious")
    # FILE_TOO_LARGE_TO_ANALYZE = (
    #     "file_too_large_to_analyze",
    #     _("File too large to analyze"),
    # )
    READY = "ready", _("Ready")


class FileAudioExtractionStateChoices(models.TextChoices):
    """Possible states of the validated audio representation of a file."""

    PENDING_AUDIO_EXTRACTION = "pending_audio_extraction", _("Pending audio extraction")
    EXTRACTING_AUDIO = "extracting_audio", _("Extracting audio")
    EXTRACTION_DONE = "extraction_done", _("Audio extraction done")
    AUDIO_EXTRACTION_FAILED = "audio_extraction_failed", _("Audio extraction failed")


class FileLifecycleStateChoices(models.TextChoices):
    """Possible lifecycle states of a file."""

    ACTIVE = "active", _("Active")
    PENDING_ORIGINAL_DATA_DELETION = (
        "pending_original_data_deletion",
        _("Pending original data deletion"),
    )
    ORIGINAL_DATA_DELETED = "original_data_deleted", _("Original data deleted")
    PENDING_AUTO_HARD_DELETE = "pending_auto_hard_delete", _("Pending auto hard delete")


class FileTypeChoices(models.TextChoices):
    """Defines the possible types of a file."""

    AUDIO_RECORDING = "audio_recording", _("Audio recording")


class FileSourceChoices(models.TextChoices):
    """Defines the possible source of a file."""

    UNKNOWN = "unknown", _("Unknown")
    WEB_RECORDING = "web_recording", _("Web recording")
    WEB_FILE_UPLOAD = "web_file_upload", _("Web file upload")
    MOBILE_RECORDING = "mobile_recording", _("Mobile recording")
    MOBILE_FILE_UPLOAD = "mobile_file_upload", _("Mobile file upload")


class File(BaseModel):
    """File uploaded by a user."""

    type = models.CharField(
        max_length=25,
        choices=FileTypeChoices.choices,
        null=False,
        blank=False,
    )
    title = models.CharField(_("title"), max_length=255)
    creator = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="files_created",
        blank=True,
        null=True,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    hard_deleted_at = models.DateTimeField(null=True, blank=True)

    filename = models.CharField(max_length=255, null=False, blank=False)
    duration_seconds = models.FloatField()

    upload_state = models.CharField(
        max_length=25,
        choices=FileUploadStateChoices.choices,
    )
    audio_extraction_state = models.CharField(
        max_length=30,
        choices=FileAudioExtractionStateChoices.choices,
        default=FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION,
    )
    lifecycle_state = models.CharField(
        max_length=30,
        choices=FileLifecycleStateChoices.choices,
        default=FileLifecycleStateChoices.ACTIVE,
    )
    mimetype = models.CharField(max_length=255, null=True, blank=True)
    size = models.BigIntegerField(null=True, blank=True)
    language = models.CharField(
        max_length=2,
        choices=ISO_639_1_CHOICES,
        default="fr",
    )
    description = models.TextField(null=True, blank=True)
    malware_detection_info = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        help_text=_("Malware detection info when the analysis status is unsafe."),
    )
    source = models.CharField(
        max_length=25,
        choices=FileSourceChoices.choices,
        default=FileSourceChoices.UNKNOWN,
    )
    storage_bucket_name = models.CharField(max_length=63)
    original_file_data_delete_at = models.DateTimeField()
    original_file_data_delete_at_with_grace_period = models.DateTimeField()
    file_auto_hard_delete_at = models.DateTimeField()
    file_auto_hard_delete_at_with_grace_period = models.DateTimeField()
    trashbin_purge_at = models.DateTimeField(null=True, blank=True)
    trashbin_purge_at_with_grace_period = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "file"
        verbose_name = _("File")
        verbose_name_plural = _("Files")
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["creator", "type", "-created_at"]),
            # To ease with the deletion queries
            models.Index(fields=["-created_at"]),
            models.Index(
                fields=["storage_bucket_name", "created_at"],
                name="file_bucket_created_at_idx",
            ),
            models.Index(
                fields=["storage_bucket_name", "deleted_at"],
                name="file_bucket_deleted_at_idx",
            ),
            models.Index(
                fields=["original_file_data_delete_at"],
                name="file_original_delete_at_idx",
            ),
            models.Index(
                fields=["original_file_data_delete_at_with_grace_period"],
                name="file_original_delete_grace_idx",
            ),
            models.Index(
                fields=["file_auto_hard_delete_at"],
                name="file_hard_delete_at_idx",
            ),
            models.Index(
                fields=["file_auto_hard_delete_at_with_grace_period"],
                name="file_hard_delete_grace_idx",
            ),
            models.Index(
                fields=["trashbin_purge_at"],
                name="file_trashbin_purge_at_idx",
            ),
            models.Index(
                fields=["trashbin_purge_at_with_grace_period"],
                name="file_trashbin_purge_grace_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(trashbin_purge_at__isnull=True)
                    & Q(trashbin_purge_at_with_grace_period__isnull=True)
                )
                | (
                    Q(trashbin_purge_at__isnull=False)
                    & Q(trashbin_purge_at_with_grace_period__isnull=False)
                ),
                name="file_trashbin_deadlines",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        original_file_data_delete_at__lte=(
                            F("original_file_data_delete_at_with_grace_period")
                        )
                    )
                ),
                name="file_original_deadline_order",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        file_auto_hard_delete_at__lte=F(
                            "file_auto_hard_delete_at_with_grace_period"
                        )
                    )
                ),
                name="file_hard_delete_deadline_order",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        Q(trashbin_purge_at__isnull=True)
                        & Q(trashbin_purge_at_with_grace_period__isnull=True)
                    )
                    | Q(trashbin_purge_at__lte=F("trashbin_purge_at_with_grace_period"))
                ),
                name="file_trashbin_deadline_order",
            ),
        ]

    def __str__(self):
        return str(self.title)

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Set the upload state to pending if it's the first save and it's a file."""

        is_new = self._state.adding
        if is_new:
            self.upload_state = FileUploadStateChoices.PENDING
            self.lifecycle_state = FileLifecycleStateChoices.ACTIVE
            # The snapshot fields are required at the database level. Populate
            # provisional values before the insert; they are recalculated below
            # once auto_now_add has assigned created_at.
            self._set_configuration_snapshot(timezone.now())

        super().save(*args, **kwargs)
        if is_new:
            self._set_configuration_snapshot()
            super().save(
                update_fields=[
                    "storage_bucket_name",
                    "original_file_data_delete_at",
                    "original_file_data_delete_at_with_grace_period",
                    "file_auto_hard_delete_at",
                    "file_auto_hard_delete_at_with_grace_period",
                ]
            )

    def _set_configuration_snapshot(self, reference_time=None):
        """Persist the configuration selected by the creator's email domain."""
        profile = get_profile_for_email(self.creator.email if self.creator_id else None)
        reference_time = reference_time or self.created_at
        for field, value in profile.as_file_snapshot(reference_time).items():
            setattr(self, field, value)

    @property
    def configuration(self):
        """Return this file's persisted policy and storage configuration."""
        return get_profile_for_file(self)

    def delete(self, using=None, keep_parents=False):
        if self.deleted_at is None:
            raise RuntimeError("The file must be soft deleted before being deleted.")

        return super().delete(using, keep_parents)

    @property
    def is_ready(self):
        """Return whether the file is in a ready state"""
        return self.upload_state == FileUploadStateChoices.READY

    @property
    def extension(self):
        """Return the extension related to the filename."""
        if self.filename is None:
            raise RuntimeError(
                "The file must have a filename to compute its extension."
            )

        _, extension = splitext(self.filename)

        if extension:
            return extension.lstrip(".")

        return None

    @property
    def key_base(self):
        """Key base of the location where the file is stored in object storage."""
        if not self.pk:
            raise RuntimeError(
                "The file instance must be saved before requesting a storage key."
            )

        return f"{settings.FILE_UPLOAD_PATH}/{self.pk!s}"

    @property
    def temporary_key_base(self):
        """Temporary key base used while upload is still pending."""
        if not self.pk:
            raise RuntimeError(
                "The file instance must be saved before requesting a storage key."
            )

        return f"{settings.FILE_UPLOAD_TMP_PATH}/{self.pk!s}"

    @property
    def file_key(self):
        """Key used to store the file in object storage."""
        _, extension = splitext(self.filename)
        # We store only the extension in the storage system to avoid
        # leaking Personal Information in logs, etc.
        return f"{self.key_base}{extension!s}"

    @property
    def temporary_file_key(self):
        """Temporary key used to upload the file before it is finalized."""
        _, extension = splitext(self.filename)
        return f"{self.temporary_key_base}{extension!s}"

    @property
    def audio_file_key(self):
        """Key used to store the validated OGG audio representation."""
        return f"{self.key_base}.audio.ogg"

    def get_abilities(self, user):
        """
        Compute and return abilities for a given user on the file.
        """
        # Characteristics that are based only on specific access
        is_creator = user == self.creator
        retrieve = is_creator
        is_deleted = self.deleted_at is not None
        is_hard_deleted = self.hard_deleted_at is not None
        can_update = is_creator and not is_deleted and user.is_authenticated
        can_hard_delete = (
            is_creator and user.is_authenticated and not is_hard_deleted and is_deleted
        )
        can_destroy = is_creator and not is_deleted and user.is_authenticated
        can_restore = (
            is_creator and is_deleted and user.is_authenticated and not is_hard_deleted
        )

        return {
            "destroy": can_destroy,
            "hard_delete": can_hard_delete,
            "retrieve": retrieve,
            "media_auth": retrieve and not is_hard_deleted,
            "partial_update": can_update,
            "update": can_update,
            "upload_ended": can_update and user.is_authenticated,
            "restore": can_restore,
        }

    @transaction.atomic
    def soft_delete(self):
        """
        Soft delete the file.
        We still keep the .delete() method untouched for programmatic purposes.
        """
        if self.deleted_at:
            raise RuntimeError("This file is already deleted.")

        self.deleted_at = timezone.now()
        profile = get_profile_for_email(self.creator.email if self.creator_id else None)
        for field, value in profile.as_trashbin_snapshot(self.deleted_at).items():
            setattr(self, field, value)
        self.save(
            update_fields=[
                "deleted_at",
                "trashbin_purge_at",
                "trashbin_purge_at_with_grace_period",
            ]
        )

    def hard_delete(self):
        """
        Hard delete the file.
        We still keep the .delete() method untouched for programmatic purposes.
        """
        if self.hard_deleted_at:
            raise ValidationError(
                {
                    "hard_deleted_at": ValidationError(
                        _("This file is already hard deleted."),
                        code="file_hard_delete_already_effective",
                    )
                }
            )

        if self.deleted_at is None:
            raise ValidationError(
                {
                    "hard_deleted_at": ValidationError(
                        _("To hard delete a file, it must first be soft deleted."),
                        code="file_hard_delete_should_soft_delete_first",
                    )
                }
            )

        self.hard_deleted_at = timezone.now()
        self.save(update_fields=["hard_deleted_at"])

    @transaction.atomic
    def restore(self):
        """Cancelling a soft delete with checks."""
        # This should not happen
        if self.deleted_at is None:
            raise ValidationError(
                {
                    "deleted_at": ValidationError(
                        _("This item is not deleted."),
                        code="item_restore_not_deleted",
                    )
                }
            )

        if timezone.now() > get_trashbin_cutoff(self):
            raise ValidationError(
                {
                    "deleted_at": ValidationError(
                        _("This item was permanently deleted and cannot be restored."),
                        code="item_restore_hard_deleted",
                    )
                }
            )

        # Restore the current item
        self.deleted_at = None
        self.trashbin_purge_at = None
        self.trashbin_purge_at_with_grace_period = None

        self.save(
            update_fields=[
                "deleted_at",
                "trashbin_purge_at",
                "trashbin_purge_at_with_grace_period",
            ]
        )


class AiJobStatusChoices(models.TextChoices):
    """Possible states of a file."""

    PENDING = "pending", _("Pending")
    SUCCESS = "success", _("Success")
    FAILED = "failed", _("Failed")


class AiJobTypeChoices(models.TextChoices):
    """Possible types of Ai Jobs."""

    TRANSCRIPT = "transcript", _("Transcript")
    SUMMARIZE = "summary", _("Summary")


class AiFileJob(BaseModel):
    """
    A job that is run to process an audio file.
    """

    remote_job_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    type = models.CharField(
        max_length=25,
        choices=AiJobTypeChoices.choices,
    )
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="ai_jobs")
    status = models.CharField(
        max_length=25,
        choices=AiJobStatusChoices.choices,
    )
    language = models.CharField(
        max_length=2,
        choices=ISO_639_1_CHOICES,
        default="fr",
    )
    docs_app_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "ai_job"
        verbose_name = _("AiJob")
        verbose_name_plural = _("AiJobs")
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["file", "type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.file.title} - {self.type} - {self.status} - {self.id}"

    def delete(self, using=None, keep_parents=False):
        """Delete the AI job and its result file from object storage."""
        logger.info(
            "Deleted AI job %s and its result file if it exists %s", self.id, self.key
        )
        key = self.key
        result = super().delete(using=using, keep_parents=keep_parents)
        storage = get_storage_for_file(self.file)
        transaction.on_commit(lambda: storage.delete(key))
        return result

    @property
    def key(self) -> str:
        """Return the S3 key for the AI job result file."""
        if self.type == AiJobTypeChoices.TRANSCRIPT:
            return f"transcripts/{self.id!s}.json"
        if self.type == AiJobTypeChoices.SUMMARIZE:
            return f"summaries/{self.id!s}.txt"
        raise ValueError(f"Unknown job type: {self.type}")

    def to_markdown(self, language: str = "en") -> str:
        """Return the AI job result as a markdown string."""
        if self.status != AiJobStatusChoices.SUCCESS:
            raise ValueError(f"Job status is not success: {self.status}")

        with get_storage_for_file(self.file).open(self.key, "rb") as result_file:
            content = result_file.read()

        if self.type == AiJobTypeChoices.TRANSCRIPT:
            whisper_response = WhisperXResponse.model_validate_json(content)
            return format_transcript_for_markdown(whisper_response, language)
        if self.type == AiJobTypeChoices.SUMMARIZE:
            # Should translate this
            return "# Résumé \n \n " + content.decode("utf-8")

        raise NotImplementedError(f"Unknown job type: {self.type}")
