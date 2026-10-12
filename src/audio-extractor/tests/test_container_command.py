"""The container watchdog requests clean shutdown and bounds hung processes."""

import os
import subprocess
import time
from pathlib import Path

import pytest

WORKER_COMMAND = Path(__file__).resolve().parents[1] / "run-worker.sh"


def worker_environment(tmp_path, *, timeout=None, command='printf "%s\\n" "$@"'):
    """Replace Python with a small executable to exercise the real shell command."""
    python = tmp_path / "python"
    python.write_text(f"#!/bin/sh\n{command}\n", encoding="utf-8")
    python.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{tmp_path}:{environment['PATH']}"
    environment.pop("AUDIO_EXTRACTOR_PROCESS_TIMEOUT_SECONDS", None)
    environment["AUDIO_EXTRACTOR_SHUTDOWN_GRACE_SECONDS"] = "1"
    if timeout is not None:
        environment["AUDIO_EXTRACTOR_PROCESS_TIMEOUT_SECONDS"] = timeout
    return environment


@pytest.mark.parametrize("timeout", [None, "300", "17"])
def test_container_command_runs_one_worker(tmp_path, timeout):
    result = subprocess.run(
        ["sh", str(WORKER_COMMAND)],
        env=worker_environment(tmp_path, timeout=timeout),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["-m", "audio_extractor"]


@pytest.mark.parametrize("timeout", ["0", "000", "-1", "invalid", "1.5"])
def test_container_command_rejects_invalid_deadlines(tmp_path, timeout):
    result = subprocess.run(
        ["sh", str(WORKER_COMMAND)],
        env=worker_environment(tmp_path, timeout=timeout),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 2
    assert (
        "Process timeout and shutdown grace must be positive integers" in result.stderr
    )
    assert result.stdout == ""


def test_container_command_kills_hung_worker(tmp_path):
    started = time.monotonic()
    result = subprocess.run(
        ["sh", str(WORKER_COMMAND)],
        env=worker_environment(tmp_path, timeout="1", command="exec sleep 30"),
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert result.returncode in {124, -9, 137}
    assert time.monotonic() - started < 5


def test_container_command_also_kills_worker_subprocesses(tmp_path):
    # A surviving child would hold the captured pipe open beyond the test timeout.
    result = subprocess.run(
        ["sh", str(WORKER_COMMAND)],
        env=worker_environment(tmp_path, timeout="1", command="sleep 30 &\nwait"),
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert result.returncode in {124, -9, 137}


def test_container_command_requests_clean_shutdown(tmp_path):
    result = subprocess.run(
        ["sh", str(WORKER_COMMAND)],
        env=worker_environment(
            tmp_path,
            timeout="1",
            command="trap 'echo cleaned; exit 0' TERM\nwhile :; do sleep 0.1; done",
        ),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 124
    assert "cleaned" in result.stdout


def test_container_command_escalates_when_term_is_ignored(tmp_path):
    result = subprocess.run(
        ["sh", str(WORKER_COMMAND)],
        env=worker_environment(
            tmp_path, timeout="1", command="trap '' TERM\nsleep 30 &\nwait"
        ),
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode in {-9, 137}
