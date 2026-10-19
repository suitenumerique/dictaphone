"""Throttling modules for the API."""

from rest_framework.throttling import UserRateThrottle


class FileCreateThrottleBurst(UserRateThrottle):
    """Limit file creation bursts per user."""

    scope = "file_create_burst"


class FileCreateThrottleSustained(UserRateThrottle):
    """Limit sustained file creation per user."""

    scope = "file_create_sustained"


class FileUploadEndedThrottleBurst(UserRateThrottle):
    """Limit upload finalization bursts per user."""

    scope = "file_upload_ended_burst"


class FileUploadEndedThrottleSustained(UserRateThrottle):
    """Limit sustained upload finalization per user."""

    scope = "file_upload_ended_sustained"


class AiJobRetryThrottleBurst(UserRateThrottle):
    """Limit transcription retry bursts per user."""

    scope = "ai_job_retry_burst"


class AiJobRetryThrottleSustained(UserRateThrottle):
    """Limit sustained transcription retries per user."""

    scope = "ai_job_retry_sustained"


class AiJobCreateInDocsThrottleBurst(UserRateThrottle):
    """Limit Docs creation bursts per user."""

    scope = "ai_job_create_in_docs_burst"


class AiJobCreateInDocsThrottleSustained(UserRateThrottle):
    """Limit sustained Docs creation per user."""

    scope = "ai_job_create_in_docs_sustained"


class AiJobResultThrottleBurst(UserRateThrottle):
    """Share a result download burst allowance per user."""

    scope = "ai_job_result_burst"


class AiJobResultThrottleSustained(UserRateThrottle):
    """Share a sustained result download allowance per user."""

    scope = "ai_job_result_sustained"
