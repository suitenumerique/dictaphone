"""Client serializers for the Dictaphone core app."""

import logging
from collections import defaultdict
from datetime import timedelta
from math import ceil
from os.path import splitext
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from timezone_field.rest_framework import TimeZoneSerializerField

from core import enums, models, utils
from core.models import (
    FileLifecycleStateChoices,
    get_original_file_data_cutoff_datetime,
)
from core.utils import floor_dt_to_bucket

logger = logging.getLogger(__name__)

AI_JOB_DEFAULT_THROUGHPUT = 30  # 30s / s

MIN_JOB_SAMPLES_THROUGHPUT_ESTIMATION = 4
# We choose 5 minutes as the window size as with a max file duration of 3H
# and per worker coefficient of 37 observed in production,
# all files should be processed within 5 minutes
# This should be parametrizable later.
THROUGHPUT_WINDOW_SECONDS: int = 5 * 60  # 5 minutes
N_THROUGHPUT_WINDOWS = 3


def compute_ai_job_throughput(job_type: models.AiJobTypeChoices) -> float:
    """Estimate processing throughput in media seconds per wall-clock second."""
    now = timezone.now()
    success_queryset = (
        models.AiFileJob.objects.filter(
            status=models.AiJobStatusChoices.SUCCESS, type=job_type
        )
        .select_related("file")
        .only("updated_at", "file__duration_seconds")
        .order_by("-updated_at")
    )

    cutoff = now - timedelta(minutes=N_THROUGHPUT_WINDOWS * THROUGHPUT_WINDOW_SECONDS)
    jobs = tuple(
        success_queryset.filter(
            updated_at__gte=cutoff,
        )
    )
    if len(jobs) < MIN_JOB_SAMPLES_THROUGHPUT_ESTIMATION:
        jobs = tuple(success_queryset[:MIN_JOB_SAMPLES_THROUGHPUT_ESTIMATION])

    if len(jobs) == 0:
        return AI_JOB_DEFAULT_THROUGHPUT

    samples_by_bucket = defaultdict(list)
    for job in jobs:
        samples_by_bucket[
            floor_dt_to_bucket(
                job.updated_at,
                THROUGHPUT_WINDOW_SECONDS,
                reference_dt=now,
            )
        ].append(job)

    throughput_by_bucket = {
        k: (
            sum(max(ai_job.file.duration_seconds, 1) for ai_job in bucket_samples)
            / THROUGHPUT_WINDOW_SECONDS
        )
        for k, bucket_samples in samples_by_bucket.items()
    }

    return sum(throughput_by_bucket.values()) / len(throughput_by_bucket)


def _build_processing_expected_end_at_by_pending_job_id() -> dict:
    """Return processing expected-end-at estimates for all pending AI jobs."""
    pending_jobs = (
        models.AiFileJob.objects.filter(status=models.AiJobStatusChoices.PENDING)
        .select_related("file")
        .only("id", "type", "created_at", "file__duration_seconds")
        .order_by("created_at", "id")
    )
    throughput_by_type = {}

    processing_expected_end_at_by_job_id = {}
    queued_media_seconds = 0.0
    now = timezone.now()
    for ai_job in pending_jobs:
        if ai_job.type not in throughput_by_type:
            throughput_by_type[ai_job.type] = compute_ai_job_throughput(ai_job.type)
        throughput = throughput_by_type[ai_job.type]
        duration_seconds = ai_job.file.duration_seconds

        waiting_seconds = int(
            ceil((queued_media_seconds + duration_seconds) / throughput)
        )
        processing_expected_end_at_by_job_id[ai_job.id] = now + timedelta(
            seconds=waiting_seconds
        )
        queued_media_seconds += duration_seconds

    return processing_expected_end_at_by_job_id


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

        expected_end_at_by_job_id = self.context.get(
            "ai_job_processing_expected_end_at_by_id",
            {},
        )
        estimate = expected_end_at_by_job_id.get(ai_job.id)
        if estimate is not None:
            return estimate

        return _build_processing_expected_end_at_by_pending_job_id().get(ai_job.id)

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
            or obj.created_at
            < get_original_file_data_cutoff_datetime(include_grace_period=False)
        ):
            return None

        return f"{settings.MEDIA_BASE_URL}{settings.MEDIA_URL}{quote(obj.file_key)}"

    def get_original_file_file_delete_at(self, obj):
        """Return the date and time when the original file data will be deleted."""
        return obj.created_at + timedelta(
            days=settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS
        )

    def get_will_auto_delete_at(self, obj):
        """Return the date and time when the file will be automatically deleted."""
        return obj.created_at + timedelta(
            days=settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS
        )

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

    class Meta:
        model = models.File
        fields = [*ListFileSerializer.Meta.fields, "policy"]
        read_only_fields = [
            *(
                field
                for field in ListFileSerializer.Meta.read_only_fields
                if field not in {"filename", "duration_seconds", "source", "language"}
            ),
            "policy",
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

    def update(self, instance, validated_data):
        raise NotImplementedError("Update method can not be used.")
