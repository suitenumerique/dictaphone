"""Shared Celery task retry configuration helpers."""

from django.conf import settings


def build_retry_task_options(*, autoretry_for):
    """Build task decorator kwargs for auto-retry with exponential backoff."""
    return {
        "autoretry_for": autoretry_for,
        "retry_backoff": settings.CELERY_TASK_RETRY_BACKOFF_SECONDS,
        "retry_backoff_max": settings.CELERY_TASK_RETRY_BACKOFF_MAX_SECONDS,
        "retry_jitter": settings.CELERY_TASK_RETRY_JITTER,
        "retry_kwargs": {
            "max_retries": settings.CELERY_TASK_RETRY_MAX_RETRIES,
        },
    }
