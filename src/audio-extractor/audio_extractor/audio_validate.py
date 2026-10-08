"""Validation of downloaded OGG Opus audio."""

from pathlib import Path

from audio_extractor.utils import _run


def _validate_opus(source: Path, timeout: float) -> None:
    """Validate an OGG Opus input using both libopusfile tools."""
    _run(["opusinfo", str(source)], timeout)
    _run(["opusdec", "--quiet", str(source), "/dev/null"], timeout)
