"""Analytics module."""

from enum import StrEnum
from logging import getLogger

from django.conf import settings
from django.core.cache import cache

import posthog

from core.models import User

logger = getLogger(__name__)


class EventName(StrEnum):
    """Analytics event names."""

    FILE_UPLOADED = "file_uploaded"
    FILE_SOFT_DELETED = "file_soft_deleted"
    FILES_LISTED = "files_listed"
    TRANSCRIPT_GENERATION_SUCCESS = "transcript_generation_success"
    TRANSCRIPT_GENERATION_FAILURE = "transcript_generation_failure"
    AUDIO_EXTRACTION_SUCCESS = "audio_extraction_success"
    AUDIO_EXTRACTION_FAILURE = "audio_extraction_failure"


def capture_event(event_name: EventName, *, user: User, properties=None) -> None:
    """
    Capture an analytics event with user properties.
    """
    if settings.POSTHOG_ENABLED:
        properties = properties or {}
        properties["$set"] = {
            "name": user.full_name,
            "email": user.email,
            "sub": user.sub,
            **properties.get("$set", {}),
        }
        posthog.capture(event_name, distinct_id=user.id, properties=properties)


def capture_files_listed(*, user: User, client_source: str) -> None:
    """Update the authenticated user's access status at most once per hour."""
    if not settings.POSTHOG_ENABLED or not user.is_authenticated:
        return

    try:
        # Atomic on the shared cache: web/mobile requests use the same allowance.
        if cache.add(f"analytics:files_listed:{user.pk}", True, timeout=3600):
            capture_event(
                EventName.FILES_LISTED,
                user=user,
                properties={
                    "client_source": client_source,
                    "$set": {"access_status": user.access_status},
                },
            )
    except Exception:  # pylint: disable=broad-exception-caught
        # Analytics/cache outages must not prevent users from listing files.
        logger.exception("Failed to capture files_listed analytics")


__all__ = ["EventName", "capture_event", "capture_files_listed"]
