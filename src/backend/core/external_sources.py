"""Restrict downloads from URLs supplied by external services."""

import logging
from urllib.parse import unquote, urlsplit

from django.conf import settings

import requests

from core.utils import redact_url

logger = logging.getLogger(__name__)


def _url_scope(url):
    """Return an unambiguous origin and decoded path for bucket matching."""
    if not isinstance(url, str) or any(ord(char) <= 32 for char in url):
        raise ValueError("Invalid external source URL")
    if "\\" in url or "#" in url:
        raise ValueError("Invalid external source URL")
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("Invalid external source URL")
    if settings.EXTERNAL_SOURCE_REQUIRE_HTTPS and parts.scheme != "https":
        raise ValueError("External source URL must use HTTPS")

    path = parts.path or "/"
    # Reject ambiguous paths, including double-encoded traversal interpreted by
    # some proxies. Do not change the original signed URL used for the request.
    for _ in range(10):
        decoded = unquote(path, errors="strict")
        if decoded == path:
            break
        path = decoded
    else:
        raise ValueError("Excessively encoded external source URL path")
    if (
        "\\" in path
        or any(ord(char) < 32 for char in path)
        or any(segment in {".", ".."} for segment in path.split("/"))
    ):
        raise ValueError("Ambiguous external source URL path")
    port = parts.port
    if port is None:
        port = 443 if parts.scheme == "https" else 80
    return (parts.scheme, parts.hostname, port), path, parts.query


def validate_external_source_url(url):
    """Authorize the origin and bucket/path, or warn when checks are disabled."""
    try:
        _validate_external_source_url(url)
    except ValueError:
        logger.warning("Rejected external source URL %r", redact_url(url))
        raise


def _validate_external_source_url(url):
    """Apply the configured download policy."""
    prefixes = settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES
    if prefixes is None:
        # URLs can contain signed credentials: never include them in warnings.
        logger.warning(
            "External source URL validation is disabled "
            "(EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES is None)"
        )
        return

    origin, path, _ = _url_scope(url)
    for prefix in prefixes:
        allowed_origin, allowed_path, query = _url_scope(prefix)
        if query:
            raise ValueError("External source URL prefixes must not contain queries")
        allowed_path = allowed_path.rstrip("/")
        if origin == allowed_origin and (
            path == allowed_path or path.startswith(allowed_path + "/")
        ):
            return
    raise ValueError("External source URL is not allowed")


def fetch_external_source(session, url):
    """Download a validated URL without following redirects to other targets."""
    validate_external_source_url(url)
    try:
        response = session.get(url, timeout=(10, 20), allow_redirects=False)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise type(exc)(
            f"External source request failed for {redact_url(url)!r}"
        ) from None
    if response.status_code in range(300, 400):
        response.close()
        logger.warning(
            "Rejected external source URL %r: redirects are not allowed",
            redact_url(url),
        )
        raise ValueError("External source URL redirects are not allowed")
    return response
