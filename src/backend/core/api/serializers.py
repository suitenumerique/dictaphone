"""Client serializers for the Dictaphone core app."""

import logging
from datetime import timedelta
from os.path import splitext
from time import perf_counter
from urllib.parse import quote

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from timezone_field.rest_framework import TimeZoneSerializerField

from core import enums, models, utils
from core.capacity_estimator import Task, estimate_tasks_eta
from core.models import (
    FileLifecycleStateChoices,
    get_original_file_data_cutoff_datetime,
)
from core.storage import get_bucket_configuration_for_file

logger = logging.getLogger(__name__)


def _build_processing_expected_end_at_by_pending_job_id() -> dict:
    """Return processing expected-end-at estimates for all pending AI jobs."""
    started_at = perf_counter()
    try:
        now = timezone.now()
        ai_jobs = (
            models.AiFileJob.objects.filter(
                Q(status=models.AiJobStatusChoices.PENDING)
                | Q(
                    status=models.AiJobStatusChoices.SUCCESS,
                    updated_at__gte=now
                    - timedelta(
                        seconds=settings.AI_JOB_ESTIMATION_CAPACITY_LOOKBACK_SECONDS
                    ),
                )
            )
            .select_related("file")
            .only(
                "id",
                "type",
                "status",
                "created_at",
                "updated_at",
                "file__duration_seconds",
                "file__audio_extraction_state",
            )
            .order_by("created_at", "id")
        )

        processing_expected_end_at_by_job_id = {}
        tasks_by_type = {}
        pending_job_ids_by_type = {}
        for ai_job in ai_jobs:
            is_pending = ai_job.status == models.AiJobStatusChoices.PENDING
            if is_pending and (
                ai_job.file.audio_extraction_state
                != models.FileAudioExtractionStateChoices.EXTRACTION_DONE
            ):
                # The transcription queue does not contain this job yet. Its
                # duration is also not authoritative until extraction completes.
                processing_expected_end_at_by_job_id[ai_job.id] = None
                continue

            duration_seconds = ai_job.file.duration_seconds
            if duration_seconds is None:
                if is_pending:
                    processing_expected_end_at_by_job_id[ai_job.id] = None
                continue

            tasks_by_type.setdefault(ai_job.type, []).append(
                Task(
                    id=str(ai_job.id),
                    created_at=ai_job.created_at,
                    weight=duration_seconds,
                    done_at=(
                        ai_job.updated_at
                        if ai_job.status == models.AiJobStatusChoices.SUCCESS
                        else None
                    ),
                ),
            )
            if is_pending:
                pending_job_ids_by_type.setdefault(ai_job.type, []).append(ai_job.id)

        for job_type, job_ids in pending_job_ids_by_type.items():
            estimates_by_task_id = estimate_tasks_eta(
                tasks_by_type[job_type],
                C=settings.AI_JOB_ESTIMATION_THROUGHPUT_PER_WORKER,
                now=now,
                default_capacity=settings.AI_JOB_ESTIMATION_DEFAULT_CAPACITY,
                capacity_lookback=timedelta(
                    seconds=settings.AI_JOB_ESTIMATION_CAPACITY_LOOKBACK_SECONDS
                ),
                capacity_window=timedelta(
                    seconds=settings.AI_JOB_ESTIMATION_CAPACITY_WINDOW_SECONDS
                ),
                capacity_step=timedelta(
                    seconds=settings.AI_JOB_ESTIMATION_CAPACITY_STEP_SECONDS
                ),
                capacity_half_life=timedelta(
                    seconds=settings.AI_JOB_ESTIMATION_CAPACITY_HALF_LIFE_SECONDS
                ),
                replay_horizon=timedelta(
                    seconds=settings.AI_JOB_ESTIMATION_REPLAY_HORIZON_SECONDS
                ),
            )
            for job_id in job_ids:
                processing_expected_end_at_by_job_id[job_id] = estimates_by_task_id[
                    str(job_id)
                ].eta

        return processing_expected_end_at_by_job_id
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Unable to compute AI job processing estimates")
        return {}
    finally:
        logger.info(
            "Computed AI job processing estimates in %.3f seconds",
            perf_counter() - started_at,
        )


class UserSerializer(serializers.ModelSerializer):
    """Serialize users."""

    timezone = TimeZoneSerializerField()

    class Meta:
        model = models.User
        fields = [
            "id",
            "email",
            "full_name",
            "short_name",
            "timezone",
            "language",
            "flag_show_mobile_app_popup",
        ]
        read_only_fields = ["id", "email", "full_name", "short_name"]


class UserLightSerializer(serializers.ModelSerializer):
    """Serialize users with limited fields."""

    class Meta:
        model = models.User
        fields = ["id", "full_name", "short_name"]
        read_only_fields = ["id", "full_name", "short_name"]


class AiJobSerializer(serializers.ModelSerializer):
    """Serialize AI job model for the API."""

    processing_expected_end_at = serializers.SerializerMethodField(read_only=True)

    def get_processing_expected_end_at(self, ai_job):
        """Return estimated processing end datetime for pending jobs."""
        if ai_job.status != models.AiJobStatusChoices.PENDING:
            return None

        context_key = "ai_job_processing_expected_end_at_by_id"
        if context_key not in self.context:
            self.context[context_key] = (
                _build_processing_expected_end_at_by_pending_job_id()
            )

        return self.context[context_key].get(ai_job.id)

    class Meta:
        model = models.AiFileJob
        fields = [
            "id",
            "type",
            "status",
            "language",
            "created_at",
            "updated_at",
            "docs_app_id",
            "processing_expected_end_at",
        ]
        read_only_fields = [
            "id",
            "type",
            "status",
            "language",
            "created_at",
            "updated_at",
            "docs_app_id",
            "processing_expected_end_at",
        ]


class AiJobRetrySerializer(serializers.Serializer):
    """Serializer for transcript retry requests."""

    language = serializers.ChoiceField(choices=enums.ISO_639_1_CHOICES)

    def create(self, validated_data):
        raise NotImplementedError()

    def update(self, instance, validated_data):
        raise NotImplementedError()


class ListFileSerializer(serializers.ModelSerializer):
    """Serialize File model for the API."""

    url = serializers.SerializerMethodField(read_only=True)
    creator = UserLightSerializer(read_only=True)
    abilities = serializers.SerializerMethodField(read_only=True)
    ai_jobs = AiJobSerializer(many=True, read_only=True)

    original_file_file_delete_at = serializers.SerializerMethodField(read_only=True)
    will_auto_delete_at = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = models.File
        fields = [
            "id",
            "created_at",
            "updated_at",
            "title",
            "type",
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
            "description",
            "url",
            "ai_jobs",
            "abilities",
            "source",
            "language",
            "original_file_file_delete_at",
            "will_auto_delete_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
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
            "url",
            "ai_jobs",
            "abilities",
            "source",
            "language",
            "original_file_file_delete_at",
            "will_auto_delete_at",
        ]

    def _ensure_ai_job_estimation_context(self):
        """Compute AI queue metrics once and share them with nested serializers."""
        if "ai_job_processing_expected_end_at_by_id" in self.context:
            return

        view = self.context.get("view")
        if view and getattr(view, "action", None) not in {"list", "retrieve"}:
            self.context["ai_job_processing_expected_end_at_by_id"] = {}
            return

        self.context["ai_job_processing_expected_end_at_by_id"] = (
            _build_processing_expected_end_at_by_pending_job_id()
        )

    def to_representation(self, instance):
        """Ensure pending AI jobs can access precomputed estimation data."""
        self._ensure_ai_job_estimation_context()
        return super().to_representation(instance)

    def get_url(self, obj):
        """Return the URL of the file."""
        if (
            not obj.is_ready
            or obj.lifecycle_state != FileLifecycleStateChoices.ACTIVE
            or timezone.now()
            >= get_original_file_data_cutoff_datetime(obj, include_grace_period=False)
        ):
            return None

        return (
            f"{settings.MEDIA_BASE_URL}{settings.MEDIA_URL}"
            f"{quote(obj.configuration.storage_bucket_name)}/{quote(obj.file_key)}"
        )

    def get_original_file_file_delete_at(self, obj):
        """Return the date and time when the original file data will be deleted."""
        return obj.configuration.original_file_data_delete_at

    def get_will_auto_delete_at(self, obj):
        """Return the date and time when the file will be automatically deleted."""
        return obj.configuration.file_auto_hard_delete_at

    def get_abilities(self, file) -> dict:
        """Return abilities of the logged-in user on the instance."""
        request = self.context.get("request")
        if not request:
            return {}

        return file.get_abilities(request.user)


class FileSerializer(ListFileSerializer):
    """Default serializer File model for the API."""

    def create(self, validated_data):
        raise NotImplementedError("Create method can not be used.")


class CreateFileSerializer(ListFileSerializer):
    """Serializer used to create a new file"""

    title = serializers.CharField(max_length=255, required=False)
    policy = serializers.SerializerMethodField()
    acl = serializers.SerializerMethodField()

    class Meta:
        model = models.File
        fields = [*ListFileSerializer.Meta.fields, "policy", "acl"]
        read_only_fields = [
            *(
                field
                for field in ListFileSerializer.Meta.read_only_fields
                if field not in {"filename", "duration_seconds", "source", "language"}
            ),
            "policy",
            "acl",
        ]

    def get_fields(self):
        """Force the id field to be writable."""
        fields = super().get_fields()
        fields["id"].read_only = False

        return fields

    def validate_id(self, value):
        """Ensure the provided ID does not already exist when creating a new file."""
        request = self.context.get("request")

        # Only check this on POST (creation)
        if request and models.File.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "A file with this ID already exists. You cannot override it.",
                code="file_create_existing_id",
            )

        return value

    def validate(self, attrs):
        """Validate extension and fill title."""
        # we run the default validation first to make sure the base data in attrs is ok
        attrs = super().validate(attrs)

        filename_root, ext = splitext(attrs["filename"])

        if settings.FILE_UPLOAD_APPLY_RESTRICTIONS:
            config_for_file_type = settings.FILE_UPLOAD_RESTRICTIONS[attrs["type"]]
            if ext.lower() not in config_for_file_type["allowed_extensions"]:
                logger.info(
                    "create_item: file extension not allowed %s for filename %s",
                    ext,
                    attrs["filename"],
                )
                raise serializers.ValidationError(
                    {"filename": _("This file extension is not allowed.")},
                    code="item_create_file_extension_not_allowed",
                )

            count = models.File.objects.filter(
                creator=self.context["request"].user,
                deleted_at__isnull=True,
                type=attrs["type"],
            ).count()
            if count >= config_for_file_type["max_count_by_user"]:
                logger.info(
                    "create_item: user reached max files per user for type %s",
                    attrs["type"],
                )
                raise serializers.ValidationError(
                    {
                        "type": _(
                            "You have reached the maximum number of files for this type."
                        )
                    },
                    code="item_create_user_reached_max_files_per_user",
                )

        # The title will be the filename if not provided
        if not attrs.get("title", None):
            attrs["title"] = filename_root

        return attrs

    def get_policy(self, file):
        """Return the policy to use if the file is a file."""

        if file.upload_state == models.FileUploadStateChoices.READY:
            return None

        return utils.generate_upload_policy(file)

    def get_acl(self, file):
        """Return the ACL to use for the file upload."""
        return get_bucket_configuration_for_file(file).upload_acl

    def update(self, instance, validated_data):
        raise NotImplementedError("Update method can not be used.")
