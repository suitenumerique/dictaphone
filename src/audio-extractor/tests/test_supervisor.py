"""Lifecycle, deadlines, and isolated child cancellation."""

import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from audio_extractor.health import HealthState
from audio_extractor.supervisor import _process_attempt, _run_child, _wait, supervise


def test_multiple_attempts_then_idle_until_recycling(lifecycle, task):
    config, _, _ = lifecycle
    task_response = Mock(status_code=200)
    task_response.json.return_value = task.model_dump()
    with (
        patch(
            "audio_extractor.supervisor.requests.get",
            side_effect=[task_response, task_response, Mock(status_code=204)],
        ) as claim,
        patch("audio_extractor.supervisor._process_attempt") as process,
    ):
        supervise(config)
    assert claim.call_count == 3
    assert process.call_count == 2


def test_api_outage_retries_without_exiting_early(lifecycle):
    config, clock, _ = lifecycle
    config = config.model_copy(update={"max_runtime_seconds": 20})
    with patch(
        "audio_extractor.supervisor.requests.get", side_effect=requests.ConnectionError
    ) as claim:
        supervise(config)
    assert claim.call_count > 2
    assert clock[0] == 20


def test_late_claim_is_drained_without_claiming_again(lifecycle, task):
    config, clock, _ = lifecycle
    response = Mock(status_code=200)
    response.json.return_value = task.model_dump()

    def claim(*_args, **_kwargs):
        clock[0] = 2
        return response

    with (
        patch("audio_extractor.supervisor.requests.get", side_effect=claim) as get,
        patch("audio_extractor.supervisor._process_attempt") as process,
    ):
        supervise(config)
    get.assert_called_once()
    process.assert_called_once()
    assert process.call_args.args[-1].draining


def test_attempt_reserves_reporting_time_and_uses_server_lease(config, task):
    task = task.model_copy(
        update={"expires_at": datetime.now(UTC) + timedelta(seconds=10)}
    )
    health = HealthState(10)
    with patch("audio_extractor.supervisor._run_child", return_value=False) as child:
        _process_attempt(config, task, time.monotonic(), threading.Event(), health)
    assert child.call_count == 2
    processing_deadline = child.call_args_list[0].args[2]
    reporting_deadline = child.call_args_list[1].args[2]
    assert 0 < reporting_deadline - processing_deadline <= 1
    assert reporting_deadline <= time.monotonic() + 10
    assert child.call_args_list[1].kwargs == {"failure": True}


def test_expired_attempt_never_starts_child(config, task):
    task = task.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    with patch("audio_extractor.supervisor._run_child") as child:
        _process_attempt(
            config, task, time.monotonic(), threading.Event(), HealthState(10)
        )
    child.assert_not_called()


def test_child_deadline_kills_descendants(config, task, tmp_path):
    real_popen = subprocess.Popen
    pid_file = tmp_path / "descendant.pid"
    # Ignore TERM deliberately: task deadlines must still bound all descendants.
    script = f"""
import signal, subprocess, pathlib, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen(['sleep', '30'])
pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))
time.sleep(30)
"""

    def popen(_command, **kwargs):
        return real_popen([sys.executable, "-c", script], **kwargs)

    with patch("audio_extractor.supervisor.subprocess.Popen", side_effect=popen):
        result = _run_child(
            config, task, time.monotonic() + 0.5, threading.Event(), HealthState(10)
        )
    assert not result
    pid = int(pid_file.read_text())
    # A killed orphan can briefly be a zombie until the host reaps it.
    try:
        state = Path(f"/proc/{pid}/stat").read_text().split()[2]
    except FileNotFoundError:
        state = None
    assert state in {None, "Z"}


def test_termination_cancels_active_child(config, task):
    stop = threading.Event()
    process = Mock(pid=12345)
    process.poll.return_value = None
    stop.set()
    with (
        patch("audio_extractor.supervisor.subprocess.Popen", return_value=process),
        patch("audio_extractor.supervisor.os.killpg") as kill,
    ):
        assert not _run_child(
            config, task, time.monotonic() + 300, stop, HealthState(10)
        )
    kill.assert_called_once_with(12345, signal.SIGKILL)
    process.wait.assert_called_once()


def test_long_retry_wait_keeps_supervisor_live(lifecycle):
    _, clock, stop = lifecycle
    health = HealthState(10)
    health.update(initialized=True)
    _wait(40, stop, health)
    assert clock[0] == 40
    assert health.status("/livez") == 200
