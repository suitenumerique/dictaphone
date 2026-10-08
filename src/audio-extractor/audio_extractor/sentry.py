"""Sentry initialization for the standalone worker."""

import re
from urllib.parse import unquote

import sentry_sdk

from audio_extractor.settings import Settings
from audio_extractor.utils import _redact_url

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


def init_sentry(settings: Settings) -> None:
    """Initialize Sentry when a DSN is configured."""
    if settings.sentry_dsn is None:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.sentry_environment,
        release=settings.sentry_release,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        enable_logs=False,
        enable_metrics=False,
        before_send=_scrub_sentry_data,
        before_send_transaction=_scrub_sentry_data,
        before_breadcrumb=_scrub_sentry_data,
    )
    sentry_sdk.set_tag("application", "audio-extractor")
