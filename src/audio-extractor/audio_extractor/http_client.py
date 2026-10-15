"""Configured process-wide HTTP session shared by the worker's request paths."""

from typing import TypedDict

import requests

from audio_extractor.settings import Settings


class _HTTPState(TypedDict):
    session: requests.Session | None
    gateway_url: str | None


_state: _HTTPState = {"session": None, "gateway_url": None}


def configure_session(config: Settings) -> requests.Session:
    """Initialize the process-wide session with this worker's identity."""
    close_session()
    session = requests.Session()
    session.headers["User-Agent"] = config.user_agent
    _state["session"] = session
    _state["gateway_url"] = config.s3_gateway_url
    return session


def get_session() -> requests.Session:
    """Return the initialized process-wide session."""
    session = _state["session"]
    if session is None:
        raise RuntimeError("HTTP session has not been configured")
    return session


def close_session() -> None:
    """Close and clear the process-wide session."""
    session = _state["session"]
    if session is not None:
        session.close()
        _state["session"] = None
    _state["gateway_url"] = None


def storage_target(
    url: str, headers: dict[str, str] | None = None
) -> tuple[str, dict[str, str]]:
    """Route storage transfers only; preserve the original signed URL in a header."""
    gateway = _state.get("gateway_url")
    headers = dict(headers or {})
    if gateway:
        headers["X-Target-URL"] = url
    return gateway or url, headers
