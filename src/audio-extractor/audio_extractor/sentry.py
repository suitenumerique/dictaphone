"""Shared Sentry initialization and URL scrubbing for workers and the gateway."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import unquote

import sentry_sdk

from audio_extractor.utils import _redact_url

if TYPE_CHECKING:
    from audio_extractor.s3_gateway.settings import GatewaySettings
    from audio_extractor.settings import Settings

_URL_PATTERN = re.compile(r"(?i)\bhttps?(?::|%3a)(?:(?:\\?/)|%2f){2}[^\s<>\"']+")


def _scrub_sentry_data(value, _hint=None):
    """Redact URL credentials, query parameters, and fragments in event data."""
    if isinstance(value, str):
        return _URL_PATTERN.sub(
            lambda match: _redact_url(unquote(match.group()).replace("\\/", "/")),
            value,
        )
    if isinstance(value, dict):
        return {
            _scrub_sentry_data(key): _scrub_sentry_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_sentry_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_sentry_data(item) for item in value)
    return value


def init_sentry(
    settings: Settings | GatewaySettings, *, application: str = "audio-extractor"
) -> None:
    """Initialize Sentry when a DSN is configured."""
    if settings.sentry_dsn is None:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=settings.release,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        enable_logs=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=_scrub_sentry_data,
        before_send_transaction=_scrub_sentry_data,
        before_breadcrumb=_scrub_sentry_data,
    )
    sentry_sdk.set_tag("application", application)
