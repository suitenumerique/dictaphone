"""Dedicated transcoding and validation job workers."""

import logging
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from audio_extractor.api_models import (
    TranscodingCompletion,
    TranscodingJob,
    ValidationCompletion,
    ValidationJob,
)
from audio_extractor.audio_transcode import _convert
from audio_extractor.audio_validate import _validate_opus
from audio_extractor.settings import Settings
from audio_extractor.utils import (
    _clean_work_dir,
    _download,
    _redact_url,
    _upload,
)

LOGGER = logging.getLogger(__name__)


def _measure_step(
    metadata: dict[str, float | int],
    name: str,
    action,
    *,
    mode: str,
    job_id: str,
):
    """Run a job step, log its outcome, and record its elapsed time."""
    LOGGER.info("%s job %s: %s started", mode, job_id, name)
    started = time.perf_counter()
    try:
        return action()
    finally:
        elapsed = round(time.perf_counter() - started, 6)
        metadata[f"{name}_seconds"] = elapsed
        LOGGER.info("%s job %s: %s ended after %.3f seconds", mode, job_id, name, elapsed)


def _authorization_headers(config: Settings) -> dict[str, str]:
    """Build the bearer header for this worker's dedicated API token."""
    return {"Authorization": f"Bearer {config.token.get_secret_value()}"}


def _log_job_failure(
    mode: str,
    job_id: str,
    source_url: str,
    exc: Exception,
    destination_url: str | None = None,
) -> None:
    """Log the error and sanitized task URLs without exposing signed queries."""
    urls = f"source_url={_redact_url(source_url)}"
    task_urls = [source_url]
    if destination_url is not None:
        urls += f" destination_url={_redact_url(destination_url)}"
        task_urls.append(destination_url)
    message = str(exc)
    for url in task_urls:
        query = urlsplit(url).query
        message = message.replace(url, _redact_url(url))
        if query:
            message = message.replace(f"?{query}", "")
    # Exceptions can echo signed URLs other than the task's known URLs. Match
    # URL-shaped text in the error and pass each match through the same redactor.
    message = re.sub(
        r"https?://[^\s\"'<>]+",
        lambda match: _redact_url(match.group()),
        message,
    )
    # Also strip query strings from path-like values (for example, a local
    # filename or URL path) when they are reported without an http(s) scheme.
    message = re.sub(r"(/[^\s?\"'<>]+)\?[^\s\"'<>]*", r"\1", message)
    LOGGER.error(
        "%s job %s failed (%s: %s); %s",
        mode,
        job_id,
        type(exc).__name__,
        message,
        urls,
    )


def _post_completion(
    config: Settings,
    endpoint: str,
    payload: TranscodingCompletion | ValidationCompletion,
) -> None:
    """Send a validated completion payload to its mode-specific endpoint."""
    url = urljoin(config.api_url + "/", endpoint)
    response = requests.post(
        url,
        json=payload.model_dump(exclude_none=True),
        headers=_authorization_headers(config),
        timeout=config.request_timeout,
    )
    response.raise_for_status()
    LOGGER.info("Reported %s completion for job %s", payload.status, payload.id)


def _prepare_job_directory(config: Settings) -> tempfile.TemporaryDirectory[str]:
    """Create an isolated workspace for one job."""
    config.work_dir.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="audio-job-", dir=config.work_dir)


def process_transcoding_job(config: Settings, job: TranscodingJob) -> None:
    """Download, transcode, upload, and complete one transcoding job."""
    LOGGER.info(
        "Transcoding job %s started; source_url=%s destination_url=%s",
        job.id,
        _redact_url(job.source_url),
        _redact_url(job.destination_url),
    )
    metadata: dict[str, float | int] = {}
    try:
        with _prepare_job_directory(config) as directory:
            source = Path(directory) / "source.media"
            output = Path(directory) / "audio.ogg"
            _measure_step(
                metadata,
                "download",
                lambda: _download(
                    job.source_url,
                    source,
                    config.request_timeout,
                    config.max_input_bytes,
                ),
                mode="Transcoding",
                job_id=job.id,
            )
            metadata["download_file_size_bytes"] = source.stat().st_size
            LOGGER.info(
                "Transcoding job %s downloaded %d bytes",
                job.id,
                metadata["download_file_size_bytes"],
            )
            duration = _measure_step(
                metadata,
                "convert",
                lambda: _convert(
                    source,
                    output,
                    config.command_timeout,
                    output_sample_rate=config.output_sample_rate,
                    output_bitrate=config.output_bitrate,
                ),
                mode="Transcoding",
                job_id=job.id,
            )
            metadata["result_file_size_bytes"] = output.stat().st_size
            LOGGER.info(
                "Transcoding job %s produced %d bytes of audio (%.3f seconds)",
                job.id,
                metadata["result_file_size_bytes"],
                duration,
            )
            _measure_step(
                metadata,
                "upload",
                lambda: _upload(
                    job.destination_url,
                    output,
                    config.request_timeout,
                    destination_headers=job.destination_headers,
                ),
                mode="Transcoding",
                job_id=job.id,
            )
        payload = TranscodingCompletion(
            id=job.id,
            status="success",
            duration_seconds=duration,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        _log_job_failure(
            "Transcoding",
            job.id,
            job.source_url,
            exc,
            destination_url=job.destination_url,
        )
        payload = TranscodingCompletion(
            id=job.id,
            status="failure",
            error=str(exc).strip()[:1000] or type(exc).__name__,
            metadata=metadata,
        )
    LOGGER.info("Transcoding job %s finished with status %s", job.id, payload.status)
    _post_completion(config, "audio-jobs/transcoding/complete", payload)


def process_validation_job(config: Settings, job: ValidationJob) -> None:
    """Download, validate, and complete one validation job."""
    LOGGER.info(
        "Validation job %s started; source_url=%s",
        job.id,
        _redact_url(job.source_url),
    )
    metadata: dict[str, float | int] = {}
    try:
        with _prepare_job_directory(config) as directory:
            source = Path(directory) / "source.media"
            _measure_step(
                metadata,
                "download",
                lambda: _download(
                    job.source_url,
                    source,
                    config.request_timeout,
                    config.max_input_bytes,
                ),
                mode="Validation",
                job_id=job.id,
            )
            metadata["download_file_size_bytes"] = source.stat().st_size
            LOGGER.info(
                "Validation job %s downloaded %d bytes",
                job.id,
                metadata["download_file_size_bytes"],
            )
            _measure_step(
                metadata,
                "validate",
                lambda: _validate_opus(source, config.command_timeout),
                mode="Validation",
                job_id=job.id,
            )
        payload = ValidationCompletion(id=job.id, status="success", metadata=metadata)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        _log_job_failure("Validation", job.id, job.source_url, exc)
        payload = ValidationCompletion(
            id=job.id,
            status="failure",
            error=str(exc).strip()[:1000] or type(exc).__name__,
            metadata=metadata,
        )
    LOGGER.info("Validation job %s finished with status %s", job.id, payload.status)
    _post_completion(config, "audio-jobs/validation/complete", payload)


def run_transcoding_worker(config: Settings) -> None:
    """Poll and process one job from the transcoding queue."""
    url = urljoin(config.api_url, "/audio-jobs/transcoding/next")
    LOGGER.info("Polling the transcoding queue")
    response = requests.get(
        url,
        headers=_authorization_headers(config),
        timeout=config.request_timeout,
    )
    if response.status_code == 204:
        LOGGER.info("No transcoding job is available")
        return
    response.raise_for_status()
    job = TranscodingJob.model_validate(response.json())
    LOGGER.info("Received transcoding job %s", job.id)
    process_transcoding_job(config, job)


def run_validation_worker(config: Settings) -> None:
    """Poll and process one job from the validation queue."""
    url = urljoin(config.api_url, "/audio-jobs/validation/next")
    LOGGER.info("Polling the validation queue")
    response = requests.get(
        url,
        headers=_authorization_headers(config),
        timeout=config.request_timeout,
    )
    if response.status_code == 204:
        LOGGER.info("No validation job is available")
        return
    response.raise_for_status()
    job = ValidationJob.model_validate(response.json())
    LOGGER.info("Received validation job %s", job.id)
    process_validation_job(config, job)


def run(config: Settings) -> None:
    """Run the worker selected by AUDIO_EXTRACTOR_MODE."""
    LOGGER.info("Audio extractor starting in %s mode", config.mode)
    _clean_work_dir(config.work_dir)
    try:
        if config.mode == "transcoding":
            run_transcoding_worker(config)
        elif config.mode == "validation":
            run_validation_worker(config)
        else:
            raise ValueError(f"Invalid mode: {config.mode}")
    finally:
        _clean_work_dir(config.work_dir)
        LOGGER.info("Audio extractor finished in %s mode", config.mode)
