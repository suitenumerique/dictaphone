"""Shared command, download, upload, and work-directory helpers."""

import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import ParamSpec, TypeVar
from urllib.parse import urlsplit, urlunsplit

import requests

LOGGER = logging.getLogger(__name__)

CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
P = ParamSpec("P")
R = TypeVar("R")


class ProcessingError(RuntimeError):
    """Raised when a media file cannot be processed or validated."""


def retry(
    *,
    retries: int = 3,
    exceptions: tuple[type[Exception], ...] = (requests.RequestException,),
    delay_seconds: float = 0.5,
    retry_if: Callable[[Exception], bool] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry a function up to ``retries`` times after its initial attempt."""
    if retries < 0:
        raise ValueError("retries must not be negative")

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(retries + 1):
                try:
                    return function(*args, **kwargs)
                except exceptions as exc:
                    if attempt == retries or (retry_if and not retry_if(exc)):
                        raise
                    LOGGER.info(
                        "Retrying %s after %s",
                        function.__name__,
                        type(exc).__name__,
                    )
                    time.sleep(delay_seconds * (2**attempt))
            raise AssertionError("retry loop ended unexpectedly")

        return wrapped

    return decorate


def _is_retryable_transfer_error(exc: Exception) -> bool:
    """Retry network errors, rate limits, and server errors only."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status_code = exc.response.status_code
        return status_code == 429 or status_code >= 500
    return isinstance(
        exc,
        (
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


def _run(command: list[str], timeout: float, *, capture_output: bool = False) -> str:
    """Run a fixed media command with a hard timeout."""
    try:
        result = subprocess.run(  # noqa: S603 - command is assembled internally
            command,
            check=True,
            stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        details = getattr(exc, "stderr", None)
        raise ProcessingError(
            f"Media command failed: {str(details or exc).strip()}"
        ) from exc
    return result.stdout or ""


@retry(retries=3, retry_if=_is_retryable_transfer_error)
def _download(url: str, destination: Path, timeout: float, max_bytes: int) -> None:
    """Stream an input media object to the bounded work volume."""
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise ProcessingError(
                            "Source media exceeds the configured size limit"
                        )
                    output.write(chunk)


@retry(retries=3, retry_if=_is_retryable_transfer_error)
def _upload(
    url: str,
    source: Path,
    timeout: float,
    destination_headers: dict[str, str] | None = None,
) -> None:
    """Upload an OGG file directly to its signed destination URL."""
    headers = {"Content-Type": "audio/ogg", **(destination_headers or {})}
    with source.open("rb") as media:
        response = requests.put(url, data=media, headers=headers, timeout=timeout)
        response.raise_for_status()


def _clean_work_dir(work_dir: Path) -> None:
    """Remove all files safely, including links left by a previous task."""
    work_dir.mkdir(parents=True, exist_ok=True)
    for item in work_dir.iterdir():
        if item.is_symlink() or not item.is_dir():
            item.unlink(missing_ok=True)
        else:
            shutil.rmtree(item, ignore_errors=True)


def _redact_url(url: str) -> str:
    """Remove URL credentials, query parameters, and fragments before logging."""
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
