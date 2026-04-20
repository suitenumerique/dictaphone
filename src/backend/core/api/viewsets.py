"""API endpoints"""
# pylint: disable=too-many-lines

import re
from logging import getLogger
from urllib.parse import unquote, urljoin, urlparse

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from django_filters import rest_framework as django_filters
from pydantic import ValidationError
from rest_framework import (
    decorators,
    filters,
    mixins,
    pagination,
    viewsets,
)
from rest_framework import (
    exceptions as drf_exceptions,
)
from rest_framework import (
    response as drf_response,
)
from rest_framework import (
    status as drf_status,
)

from core import analytics, models, utils, webhook_models
from core.api.filters import ListFileFilter
from core.authentication.webhooks import AiWebhookAuthentication
from core.tasks.file import (
    call_transcribe_service,
    handle_transcript_received,
    process_file_deletion,
    store_summary,
)

from ..models import AiFileJob, AiJobStatusChoices, AiJobTypeChoices
from . import permissions, serializers

# pylint: disable=too-many-ancestors

logger = getLogger(__name__)

FILE_FOLDER = settings.FILE_UPLOAD_PATH
UUID_REGEX = (
    r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
)
FILE_EXT_REGEX = r"[\d\w]+"
MEDIA_STORAGE_URL_PATTERN = re.compile(
    f"{settings.MEDIA_URL:s}"
    rf"(?P<key>{FILE_FOLDER:s}/(?P<pk>{UUID_REGEX:s})\.{FILE_EXT_REGEX:s})$"
)


class NestedGenericViewSet(viewsets.GenericViewSet):
    """
    A generic Viewset aims to be used in a nested route context.
    e.g: `/api/v1.0/resource_1/<resource_1_pk>/resource_2/<resource_2_pk>/`

    It allows to define all url kwargs and lookup fields to perform the lookup.
    """

    lookup_fields: list[str] = ["pk"]
    lookup_url_kwargs: list[str] = []

    def __getattribute__(self, file):
        """
        This method is overridden to allow to get the last lookup field or lookup url kwarg
        when accessing the `lookup_field` or `lookup_url_kwarg` attribute. This is useful
        to keep compatibility with all methods used by the parent class `GenericViewSet`.
        """
        if file in ["lookup_field", "lookup_url_kwarg"]:
            return getattr(self, file + "s", [None])[-1]

        return super().__getattribute__(file)

    def get_queryset(self):
        """
        Get the list of files for this view.

        `lookup_fields` attribute is enumerated here to perform the nested lookup.
        """
        queryset = super().get_queryset()

        # The last lookup field is removed to perform the nested lookup as it corresponds
        # to the object pk, it is used within get_object method.
        lookup_url_kwargs = (
            self.lookup_url_kwargs[:-1]
            if self.lookup_url_kwargs
            else self.lookup_fields[:-1]
        )

        filter_kwargs = {}
        for index, lookup_url_kwarg in enumerate(lookup_url_kwargs):
            if lookup_url_kwarg not in self.kwargs:
                raise KeyError(
                    f"Expected view {self.__class__.__name__} to be called with a URL "
                    f'keyword argument named "{lookup_url_kwarg}". Fix your URL conf, or '
                    "set the `.lookup_fields` attribute on the view correctly."
                )

            filter_kwargs.update(
                {self.lookup_fields[index]: self.kwargs[lookup_url_kwarg]}
            )

        return queryset.filter(**filter_kwargs)


class SerializerPerActionMixin:
    """
    A mixin to allow to define serializer classes for each action.

    This mixin is useful to avoid to define a serializer class for each action in the
    `get_serializer_class` method.
    """

    serializer_classes: dict[str, type] = {}
    default_serializer_class: type = None

    def get_serializer_class(self):
        """
        Return the serializer class to use depending on the action.
        """
        return self.serializer_classes.get(self.action, self.default_serializer_class)


class Pagination(pagination.PageNumberPagination):
    """Pagination to display no more than 100 objects per page sorted by creation date."""

    ordering = "-created_on"
    max_page_size = 100
    page_size_query_param = "page_size"


class UserViewSet(
    mixins.UpdateModelMixin, viewsets.GenericViewSet, mixins.ListModelMixin
):
    """User ViewSet"""

    permission_classes = [permissions.IsSelf]
    queryset = models.User.objects.all()
    serializer_class = serializers.UserSerializer

    def get_queryset(self):
        """
        Limit listed users by querying the email field with a trigram similarity
        search if a query is provided.
        Limit listed users by excluding users already in the document if a document_id
        is provided.
        """
        queryset = self.queryset

        if self.action == "list":
            if not settings.ALLOW_UNSECURE_USER_LISTING:
                return models.User.objects.none()

            # Filter users by email similarity
            if query := self.request.GET.get("q", ""):
                queryset = queryset.filter(email__trigram_word_similar=query)

        return queryset

    @decorators.action(
        detail=False,
        methods=["get"],
        url_name="me",
        url_path="me",
        permission_classes=[permissions.IsAuthenticated],
    )
    def get_me(self, request):
        """
        Return information on currently logged user
        """
        context = {"request": request}
        return drf_response.Response(
            self.serializer_class(request.user, context=context).data
        )


# pylint: disable=too-many-public-methods
class FileViewSet(
    SerializerPerActionMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    FileViewSet API.

    This viewset provides CRUD operations and additional actions for managing files.

    ### API Endpoints:
    1. **List**: Retrieve a paginated list of files.
       Example: GET /files/?page=2
    2. **Retrieve**: Get a specific file by its ID.
       Example: GET /files/{id}/
    3. **Create**: Create a new file.
       Example: POST /files/
    4. **Update**: Update a file by its ID.
       Example: PUT /files/{id}/
    5. **Delete**: Soft delete a file by its ID.
       Example: DELETE /files/{id}/


    ### Ordering: created_at, updated_at, title

        Example:
        - Ascending: GET /api/v1.0/files/?ordering=created_at

    ### Filtering:
        - `is_creator_me=true`: Returns files created by the current user.
        - `is_creator_me=false`: Returns files created by other users.
        - `is_deleted=false`: Returns files that are not (soft) deleted

        Example:
        - GET /api/v1.0/files/?is_creator_me=true
        - GET /api/v1.0/files/?is_creator_me=false&is_deleted=false

    ### Notes:
    - Implements soft delete logic to retain file
    """

    ordering = ["-updated_at"]
    ordering_fields = ["created_at", "updated_at", "title"]
    pagination_class = Pagination
    permission_classes = [
        permissions.FilePermission,
    ]
    queryset = models.File.objects.filter(hard_deleted_at__isnull=True)
    default_serializer_class = serializers.FileSerializer
    serializer_classes = {
        "retrieve": serializers.ListFileSerializer,
        "list": serializers.ListFileSerializer,
        "create": serializers.CreateFileSerializer,
    }
    filter_backends = (django_filters.DjangoFilterBackend, filters.OrderingFilter)
    filterset_class = ListFileFilter

    def get_queryset(self):
        """Get queryset that defaults to the the current request user."""
        user = self.request.user
        queryset = (
            super()
            .get_queryset()
            .select_related("creator")
            .prefetch_related(
                Prefetch("ai_jobs", queryset=AiFileJob.objects.order_by("-created_at"))
            )
        )

        if not user.is_authenticated:
            return queryset.none()

        # For now, we force the filtering on the current user in all cases, might evolve later
        queryset = queryset.filter(creator=user)
        return queryset

    def get_response_for_queryset(self, queryset, context=None):
        """Return paginated response for the queryset if requested."""
        context = context or self.get_serializer_context()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context=context)
            result = self.get_paginated_response(serializer.data)
            return result

        serializer = self.get_serializer(queryset, many=True, context=context)
        return drf_response.Response(serializer.data)

    def perform_create(self, serializer):
        """Set the current user as creator of the newly created file."""

        if settings.FILE_UPLOAD_APPLY_RESTRICTIONS:
            file_type = serializer.validated_data["type"]
            config_for_file_type = settings.FILE_UPLOAD_RESTRICTIONS[file_type]

            count = models.File.objects.filter(
                creator=self.request.user,
                deleted_at__isnull=True,
                type=file_type,
            ).count()

            if count >= config_for_file_type["max_count_by_user"]:
                logger.info(
                    "create_item: user reached max files per user for type %s",
                    file_type,
                )
                raise drf_exceptions.PermissionDenied(
                    _("You have reached the maximum number of files for this type.")
                )

        serializer.save(creator=self.request.user)

    def perform_destroy(self, instance):
        """Override to implement a soft delete instead of dumping the record in database."""
        instance.soft_delete()
        analytics.capture_event(
            analytics.EventName.FILE_SOFT_DELETED,
            user=self.request.user,
            properties={
                "duration_seconds": instance.duration_seconds,
                "mimetype": instance.mimetype,
                "size": instance.size,
                "id": instance.id,
                "lifespan_seconds": (
                    instance.deleted_at - instance.created_on
                ).total_seconds(),
            },
        )

    @decorators.action(detail=True, methods=["post"], url_path="upload-ended")
    def upload_ended(self, request, *args, **kwargs):
        """
        Check the actual uploaded file and mark it as ready.
        """

        file = self.get_object()

        if not file.is_pending_upload:
            raise drf_exceptions.ValidationError(
                {"file": "This action is only available for files in PENDING state."},
                code="file_upload_state_not_pending",
            )

        s3_client = default_storage.connection.meta.client

        head_response = s3_client.head_object(
            Bucket=default_storage.bucket_name, Key=file.file_key
        )
        file_size = head_response["ContentLength"]

        if settings.FILE_UPLOAD_APPLY_RESTRICTIONS:
            config_for_file_type = settings.FILE_UPLOAD_RESTRICTIONS[file.type]
            if file_size > config_for_file_type["max_size"]:
                self._complete_file_deletion(file)
                logger.info(
                    "upload_ended: file size (%s) for file %s higher than the allowed max size",
                    file_size,
                    file.file_key,
                )
                raise drf_exceptions.ValidationError(
                    detail="The file size is higher than the allowed max size.",
                    code="file_size_exceeded",
                )

        # python-magic recommends using at least the first 2048 bytes
        # to reduce incorrect identification.
        # This is a tradeoff between pulling in the whole file and the most likely relevant bytes
        # of the file for mime type identification.
        if file_size > 2048:
            range_response = s3_client.get_object(
                Bucket=default_storage.bucket_name,
                Key=file.file_key,
                Range="bytes=0-2047",
            )
            file_head = range_response["Body"].read()
        else:
            file_head = s3_client.get_object(
                Bucket=default_storage.bucket_name, Key=file.file_key
            )["Body"].read()

        # Use improved MIME type detection combining magic bytes and file extension
        logger.info("upload_ended: detecting mimetype for file: %s", file.file_key)
        mimetype = utils.detect_mimetype(file_head, filename=file.filename)

        if mimetype == "video/mp4" and head_response["ContentType"] in {
            "audio/mp4",
            "audio/x-m4a",
        }:
            logger.info(
                "upload_ended: detected mimetype for file %s is video/mp4 "
                "but it was declared as audio/mp4, leaving it that way.",
                file.file_key,
            )
            mimetype = head_response["ContentType"]

        if settings.FILE_UPLOAD_APPLY_RESTRICTIONS:
            config_for_file_type = settings.FILE_UPLOAD_RESTRICTIONS[file.type]
            allowed_file_mimetypes = config_for_file_type["allowed_mimetypes"]
            if mimetype not in allowed_file_mimetypes:
                self._complete_file_deletion(file)
                logger.warning(
                    "upload_ended: mimetype not allowed %s for file %s",
                    mimetype,
                    file.file_key,
                )
                raise drf_exceptions.ValidationError(
                    detail="The file type is not allowed.",
                    code="file_type_not_allowed",
                )

        file.upload_state = models.FileUploadStateChoices.READY
        file.mimetype = mimetype
        file.size = file_size

        file.save(update_fields=["upload_state", "mimetype", "size"])

        if head_response["ContentType"] != mimetype:
            logger.info(
                "upload_ended: content type mismatch between object storage and file,"
                " updating from %s to %s",
                head_response["ContentType"],
                mimetype,
            )
            s3_client.copy_object(
                Bucket=default_storage.bucket_name,
                Key=file.file_key,
                CopySource={
                    "Bucket": default_storage.bucket_name,
                    "Key": file.file_key,
                },
                ContentType=mimetype,
                Metadata=head_response["Metadata"],
                MetadataDirective="REPLACE",
            )

        # Not yet implemented
        # Change the file.upload_state when this will be done
        # malware_detection.analyse_file(file.file_key, file_id=file.id)

        serializer = self.get_serializer(file)

        call_transcribe_service.delay(file.id)

        analytics.capture_event(
            analytics.EventName.FILE_UPLOADED,
            user=request.user,
            properties={
                "duration_seconds": file.duration_seconds,
                "mimetype": file.mimetype,
                "size": file.size,
                "id": file.id,
            },
        )

        return drf_response.Response(serializer.data, status=drf_status.HTTP_200_OK)

    @decorators.action(detail=True, methods=["delete"], url_path="hard-delete")
    def hard_delete(self, request, *args, **kwargs):
        """
        Hard delete a file.
        """
        instance = self.get_object()
        instance.hard_delete()
        process_file_deletion.delay(instance.id)
        return drf_response.Response(status=drf_status.HTTP_204_NO_CONTENT)

    @decorators.action(
        detail=True,
        methods=["post"],
    )
    def restore(self, request, *args, **kwargs):
        """
        Restore a soft-deleted file if it was deleted less than x days ago.
        """
        file = self.get_object()
        file.restore()

        return drf_response.Response(
            {"detail": "file has been successfully restored."},
            status=drf_status.HTTP_200_OK,
        )

    def _complete_file_deletion(self, file):
        """Delete a file completely."""
        file.soft_delete()
        file.hard_delete()
        process_file_deletion.delay(file.id)

    def _authorize_subrequest(self, request, pattern):
        """
        Authorize access based on the original URL of an Nginx subrequest
        and user permissions. Returns a dictionary of URL parameters if authorized.

        The original url is passed by nginx in the "HTTP_X_ORIGINAL_URL" header.
        See corresponding ingress configuration in Helm chart and read about the
        nginx.ingress.kubernetes.io/auth-url annotation to understand how the Nginx ingress
        is configured to do this.

        Based on the original url and the logged in user, we must decide if we authorize Nginx
        to let this request go through (by returning a 200 code) or if we block it (by returning
        a 403 error). Note that we return 403 errors without any further details for security
        reasons.

        Parameters:
        - pattern: The regex pattern to extract identifiers from the URL.

        Returns:
        - A dictionary of URL parameters if the request is authorized.
        Raises:
        - PermissionDenied if authorization fails.
        """
        # Extract the original URL from the request header
        original_url = request.META.get("HTTP_X_ORIGINAL_URL")
        if not original_url:
            logger.warning("Missing HTTP_X_ORIGINAL_URL header in subrequest")
            raise drf_exceptions.PermissionDenied()

        parsed_url = urlparse(original_url)
        match = pattern.search(unquote(parsed_url.path))

        if not match:
            logger.warning(
                "Subrequest URL '%s' did not match pattern '%s'",
                parsed_url.path,
                pattern,
            )
            raise drf_exceptions.PermissionDenied()

        try:
            url_params = match.groupdict()
        except (ValueError, AttributeError) as exc:
            logger.warning("Failed to extract parameters from subrequest URL: %s", exc)
            raise drf_exceptions.PermissionDenied() from exc

        pk = url_params.get("pk")
        if not pk:
            logger.warning("File ID (pk) not found in URL parameters: %s", url_params)
            raise drf_exceptions.PermissionDenied()

        # Fetch the file and check if the user has access
        queryset = models.File.objects.all()
        # No suspicious analysis implemented yet
        # queryset = self._filter_suspicious_files(queryset, request.user)
        try:
            file = queryset.get(pk=pk)
        except models.File.DoesNotExist as exc:
            logger.warning("File with ID '%s' does not exist", pk)
            raise drf_exceptions.PermissionDenied() from exc

        user_abilities = file.get_abilities(request.user)
        if not user_abilities.get(self.action, False):
            logger.warning(
                "User '%s' lacks permission for file '%s'", request.user.id, pk
            )
            raise drf_exceptions.PermissionDenied()

        logger.debug(
            "Subrequest authorization successful. Extracted parameters: %s", url_params
        )
        return url_params, request.user.id, file

    @decorators.action(detail=False, methods=["get"], url_path="media-auth")
    def media_auth(self, request, *args, **kwargs):
        """
        This view is used by an Nginx subrequest to control access to a file's
        attachment file.

        When we let the request go through, we compute authorization headers that will be added to
        the request going through thanks to the nginx.ingress.kubernetes.io/auth-response-headers
        annotation. The request will then be proxied to the object storage backend who will
        respond with the file after checking the signature included in headers.
        """
        url_params, _, file = self._authorize_subrequest(
            request, MEDIA_STORAGE_URL_PATTERN
        )

        if file.is_pending_upload:
            logger.warning("File '%s' is not ready", file.id)
            raise drf_exceptions.PermissionDenied()

        # Generate S3 authorization headers using the extracted URL parameters
        request = utils.generate_s3_authorization_headers(f"{url_params.get('key'):s}")

        return drf_response.Response("authorized", headers=request.headers, status=200)


class AiJobViewSet(
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """AI jobs API."""

    permission_classes = [permissions.AiJobPermission]
    queryset = AiFileJob.objects.select_related("file", "file__creator")
    serializer_class = serializers.AiJobSerializer

    def get_queryset(self):
        """Restrict AI jobs to current user except webhook endpoint."""
        queryset = super().get_queryset()

        if self.action == "on_ai_event":
            return queryset

        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()

        return queryset.filter(
            file__creator=user,
            file__hard_deleted_at__isnull=True,
        )

    def _proxy_ai_result(self, ai_job, expected_type, content_type):
        """Proxy AI result file from storage."""
        if ai_job.type != expected_type:
            raise drf_exceptions.NotFound()

        if ai_job.status != AiJobStatusChoices.SUCCESS:
            raise drf_exceptions.ValidationError(
                {"status": "AI job is not completed yet."},
                code="ai_job_not_completed",
            )

        if not default_storage.exists(ai_job.key):
            raise drf_exceptions.NotFound()

        with default_storage.open(ai_job.key, "rb") as result_file:
            content = result_file.read()

        return HttpResponse(content=content, content_type=content_type, status=200)

    @decorators.action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, *args, **kwargs):
        """Return AI summary result for a summary job."""
        ai_job = self.get_object()
        return self._proxy_ai_result(
            ai_job=ai_job,
            expected_type=AiJobTypeChoices.SUMMARIZE,
            content_type="text/plain",
        )

    @decorators.action(detail=True, methods=["get"], url_path="transcript")
    def transcript(self, request, *args, **kwargs):
        """Return AI transcript result for a transcript job."""
        ai_job = self.get_object()
        return self._proxy_ai_result(
            ai_job=ai_job,
            expected_type=AiJobTypeChoices.TRANSCRIPT,
            content_type="application/json",
        )

    @decorators.action(detail=True, methods=["post"], url_path="open-in-docs")
    def open_in_docs(self, request, *args, **kwargs):
        """
        Tries to open the related document in the docs app.
        """
        ai_job = self.get_object()
        if ai_job.status != AiJobStatusChoices.SUCCESS:
            raise drf_exceptions.ValidationError(
                {"status": "AI job is not completed yet."},
                code="ai_job_not_completed",
            )

        if not ai_job.docs_app_id:
            raise drf_exceptions.NotFound(
                {"status": "Document not available yet."},
                code="document_not_available",
            )

        return drf_response.Response(
            {"doc_url": urljoin(settings.DOCS_BASE_URL, f"docs/{ai_job.docs_app_id}/")}
        )

    @decorators.action(
        detail=False,
        methods=["post"],
        url_path="webhook",
        authentication_classes=[AiWebhookAuthentication],
        permission_classes=[permissions.TranscribeWebhookPermission],
    )
    def on_ai_event(self, request):
        """Handle incoming hook events for recordings."""
        logger.debug("Received transcribe webhook event: %s", request.data)

        try:
            payload = webhook_models.webhook_payload_adapter.validate_python(
                request.data
            )
        except ValidationError as exc:
            logger.error("Invalid webhook payload: %s", exc)
            raise drf_exceptions.ValidationError(detail=exc) from exc

        ai_file_job = AiFileJob.objects.filter(remote_job_id=payload.job_id).first()
        if not ai_file_job:
            logger.warning("No AI file job found for job ID: %s", payload.job_id)
            return drf_response.Response(
                {"message": "No AI file job found for job ID, ignoring."},
            )
        if ai_file_job.status == AiJobStatusChoices.SUCCESS:
            logger.warning(
                "AI file job already in success state for job ID: %s", payload.job_id
            )
            return drf_response.Response(
                {"message": "AI file job already in success state, ignoring."},
            )

        if isinstance(payload, webhook_models.TranscribeWebhookSuccessPayload):
            handle_transcript_received.apply_async(
                args=[payload.job_id, payload.transcription_data_url]
            )
        elif isinstance(payload, webhook_models.SummarizeWebhookSuccessPayload):
            store_summary.apply_async(args=[payload.job_id, payload.summary_data_url])
        elif isinstance(
            payload,
            (
                webhook_models.SummarizeWebhookFailurePayload,
                webhook_models.TranscribeWebhookFailurePayload,
            ),
        ):
            ai_file_job.status = AiJobStatusChoices.FAILED
            ai_file_job.save()
            if isinstance(payload, webhook_models.TranscribeWebhookSuccessPayload):
                analytics.capture_event(
                    analytics.EventName.TRANSCRIPT_GENERATION_FAILURE,
                    user=ai_file_job.file.creator,
                    properties={
                        "generation_time_seconds": (
                            timezone.now() - ai_file_job.created_at
                        ).total_seconds(),
                        "ai_file_job_id": ai_file_job.id,
                        "file_id": ai_file_job.file.id,
                    },
                )

        else:
            raise NotImplementedError()

        return drf_response.Response(
            {"message": "Event processed."},
        )
