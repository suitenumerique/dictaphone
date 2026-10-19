"""Throttling modules for the API."""

from rest_framework.throttling import UserRateThrottle


class FileCreateThrottleBurst(UserRateThrottle):
    """Limit file creation bursts per user."""

    scope = "file_create_burst"


class FileCreateThrottleSustained(UserRateThrottle):
    """Limit sustained file creation per user."""

    scope = "file_create_sustained"
