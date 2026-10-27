"""Remove URL credentials from Sentry events and breadcrumbs."""

import re
from urllib.parse import unquote

_URL = re.compile(r"(?i)\bhttps?(?::|%(?:25)*3a)(?:(?:\\?/)|%(?:25)*2f){2}[^\s<>\"\']+")


def scrub_urls(value, _hint=None):
    """Remove URL queries, fragments and user credentials from nested data."""
    if isinstance(value, str):
        # Import lazily: Sentry is configured while Django settings are loading.
        # pylint: disable-next=import-outside-toplevel
        from core.utils import redact_url  # noqa: PLC0415

        def redact(match):
            candidate = match.group().replace("\\/", "/")
            for _ in range(3):
                decoded = unquote(candidate)
                if decoded == candidate:
                    break
                candidate = decoded
            # Fail closed if additional encoding remains after the decoding limit.
            if re.search(r"%[0-9a-f]{2}", candidate, re.IGNORECASE):
                return "[redacted URL]"
            return redact_url(candidate)

        return _URL.sub(redact, value)
    if isinstance(value, dict):
        return {scrub_urls(key): scrub_urls(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_urls(item) for item in value]
    return value
