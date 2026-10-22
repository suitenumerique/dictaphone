"""Shared command, download, upload, and work-directory helpers."""

import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import ParamSpec, TypeVar
from urllib.parse import urlsplit, urlunsplit

import requests

from audio_extractor.http_client import get_session, storage_target

LOGGER = logging.getLogger(__name__)

CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
STDERR_TAIL_BYTES = 64 * 1024
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


def _capture_stderr(stream, tail: bytearray) -> None:
    """Drain stderr continuously, retaining only a bounded diagnostic tail."""
    while chunk := stream.read1(8192):
        tail.extend(chunk)
        del tail[:-STDERR_TAIL_BYTES]


def _run(command: list[str], timeout: float, *, capture_output: bool = False) -> str:
    """Run a media command, retaining bounded diagnostics from both streams.

    With capture_output, return stdout separately (for example, probe JSON).
    """
    tail = bytearray()
    try:
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "rb") as reader, os.fdopen(write_fd, "wb") as writer:
            drain = threading.Thread(target=_capture_stderr, args=(reader, tail))
            drain.start()
            try:
                result = subprocess.run(  # noqa: S603 - assembled internally
                    command,
                    check=True,
                    stdout=subprocess.PIPE if capture_output else writer,
                    stderr=writer,
                    text=True,
                    timeout=timeout,
                )
            finally:
                writer.close()
                drain.join()
    except (OSError, subprocess.SubprocessError) as exc:
        details = tail.decode(errors="replace")
        if isinstance(exc, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            exc.stderr = details
        match exc:
            case subprocess.CalledProcessError(returncode=returncode):
                reason = f"{command[0]} exited with status {returncode}"
            case subprocess.TimeoutExpired():
                reason = f"{command[0]} timed out after {timeout:g} seconds"
            case _:
                reason = f"Could not run {command[0]}: {exc}"
        if details.strip():
            reason += f". {details.strip()}"
        raise ProcessingError(f"Media command failed: {reason}") from exc
    return result.stdout or ""


@retry(retries=3, retry_if=_is_retryable_transfer_error)
def _download(
    url: str,
    destination: Path,
    timeout: float,
    max_bytes: int,
) -> None:
    """Stream an input media object to the bounded work volume."""
    target, headers = storage_target(url)
    with get_session().get(
        target, headers=headers, stream=True, timeout=timeout, allow_redirects=False
    ) as response:
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


def _upload(
    url: str,
    source: Path,
    timeout: float,
    destination_headers: dict[str, str] | None = None,
) -> None:
    """Stream one PUT to storage or the gateway without automatic replay."""
    transfer_headers = {
        key: value
        for key, value in (destination_headers or {}).items()
        if key.lower() != "user-agent"
    }
    headers = {"Content-Type": "audio/ogg", **transfer_headers}
    target, headers = storage_target(url, headers)
    if target != url:
        headers["Content-Length"] = str(source.stat().st_size)
    with source.open("rb") as media:
        response = get_session().put(
            target, data=media, headers=headers, timeout=timeout, allow_redirects=False
        )
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
