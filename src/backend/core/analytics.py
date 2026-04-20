"""Analytics module."""

from enum import StrEnum

from django.conf import settings

import posthog

from core.models import User


class EventName(StrEnum):
    """Analytics event names."""

    FILE_UPLOADED = "file_uploaded"
    FILE_SOFT_DELETED = "file_soft_deleted"
    TRANSCRIPT_GENERATION_SUCCESS = "transcript_generation_success"
    TRANSCRIPT_GENERATION_FAILURE = "transcript_generation_failure"


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
        }
        posthog.capture(event_name, distinct_id=user.id, properties=properties)


__all__ = ["EventName", "capture_event"]
