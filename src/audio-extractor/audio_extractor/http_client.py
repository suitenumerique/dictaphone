"""Configured process-wide HTTP session shared by the worker's request paths."""

import requests

from audio_extractor.settings import Settings

_state: dict[str, requests.Session | None] = {"session": None}


def configure_session(config: Settings) -> requests.Session:
    """Initialize the process-wide session with this worker's identity."""
    close_session()
    session = requests.Session()
    session.headers["User-Agent"] = config.user_agent
    _state["session"] = session
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
