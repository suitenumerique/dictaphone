"""Permission handlers for the Dictaphone core app."""

import logging

from django.http import Http404

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

ACTION_FOR_METHOD_TO_PERMISSION = {
    "versions_detail": {"DELETE": "versions_destroy", "GET": "versions_retrieve"}
}

logger = logging.getLogger(__name__)


def get_access_status(request, user=None):
    """Evaluate each user's access once per request, without caching across requests."""
    if user is None:
        user = request.user
    statuses = getattr(request, "user_access_statuses", None)
    if statuses is None:
        statuses = request.user_access_statuses = {}
    if user.pk not in statuses:
        statuses[user.pk] = user.access_status
    return statuses[user.pk]


class IsAuthenticated(permissions.BasePermission):
    """
    Allows access only to authenticated users. Alternative method checking the presence
    of the auth token to avoid hitting the database.
    """

    def has_permission(self, request, view):
        return bool(request.auth) or request.user.is_authenticated


class CanProcessFiles(IsAuthenticated):
    """Keep read access while denying uploads and retries to restricted users."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if (
            view.action in {"create", "upload_ended", "retry"}
            and get_access_status(request) != "allowed"
        ):
            raise PermissionDenied(
                "Your account is restricted from uploading or retrying processing.",
                code="user_restricted",
            )
        return True


class IsSelf(IsAuthenticated):
    """
    Allows access only to authenticated users. Alternative method checking the presence
    of the auth token to avoid hitting the database.
    """

    def has_object_permission(self, request, view, obj):
        """Write permissions are only allowed to the user itself."""
        return obj == request.user


class FilePermission(IsAuthenticated):
    """
    Permissions applying to the file API endpoint.
    Handling soft deletions specificities
    """

    def has_object_permission(self, request, view, obj):
        """
        Return a 404 on deleted files or if the user is not the owner
        """
        if obj.hard_deleted_at is not None:
            raise Http404

        if obj.creator != request.user:
            raise Http404

        return obj.get_abilities(
            request.user, access_status=get_access_status(request)
        ).get(view.action, False)


class AiJobPermission(IsAuthenticated):
    """
    Permissions applying to AI job endpoints.
    """

    def has_object_permission(self, request, view, obj):
        """
        Return a 404 if AI job's file is deleted or user is not the creator.
        """
        if obj.file.hard_deleted_at is not None:
            raise Http404

        if obj.file.creator != request.user:
            raise Http404

        return True


class TranscribeWebhookPermission(permissions.BasePermission):
    """
    Permissions applying to the summary webhook endpoint.
    """

    def has_permission(self, request, view):
        return request.method == "POST"

    def has_object_permission(self, request, view, obj):
        return False
