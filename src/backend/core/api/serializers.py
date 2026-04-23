"""Client serializers for the Dictaphone core app."""

import logging
from os.path import splitext
from urllib.parse import quote

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from timezone_field.rest_framework import TimeZoneSerializerField

from core import models, utils

logger = logging.getLogger(__name__)


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

    class Meta:
        model = models.AiFileJob
        fields = ["id", "type", "status", "created_at", "updated_at", "docs_app_id"]
        read_only_fields = [
            "id",
            "type",
            "status",
            "created_at",
            "updated_at",
            "docs_app_id",
        ]


class ListFileSerializer(serializers.ModelSerializer):
    """Serialize File model for the API."""

    url = serializers.SerializerMethodField(read_only=True)
    creator = UserLightSerializer(read_only=True)
    abilities = serializers.SerializerMethodField(read_only=True)
    ai_jobs = AiJobSerializer(many=True, read_only=True)

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
            "mimetype",
            "size",
            "description",
            "url",
            "ai_jobs",
            "abilities",
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
            "mimetype",
            "size",
            "url",
            "ai_jobs",
            "abilities",
        ]

    def get_url(self, obj):
        """Return the URL of the file."""
        if obj.is_pending_upload:
            return None

        return f"{settings.MEDIA_BASE_URL}{settings.MEDIA_URL}{quote(obj.file_key)}"

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
                if field not in {"filename", "duration_seconds"}
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
