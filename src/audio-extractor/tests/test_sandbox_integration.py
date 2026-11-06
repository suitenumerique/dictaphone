"""Opt-in tests against real runsc and the image's minimal media filesystem."""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from audio_extractor.audio_transcode import _convert
from audio_extractor.audio_validate import _validate_opus
from audio_extractor.health import HealthState
from audio_extractor.sandbox import cleanup_sandbox, media_sandbox
from audio_extractor.supervisor import _run_child
from audio_extractor.utils import ProcessingError, _run

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GVISOR_TESTS") != "1", reason="Set RUN_GVISOR_TESTS=1 to run gVisor"
)


@pytest.fixture
def sandbox_config(config):
    settings = config.model_copy(
        update={
            "media_sandbox": "gvisor",
            "runsc_path": Path(os.getenv("GVISOR_RUNSC", "/usr/local/bin/runsc")),
            "sandbox_rootfs": Path(os.getenv("GVISOR_ROOTFS", "/opt/media-rootfs")),
        }
    )
    yield settings
    cleanup_sandbox(settings)


def assert_no_sandboxes(config):
    result = subprocess.run(
        [
            str(config.runsc_path),
            f"--root={config.work_dir / '.gvisor'}",
            "list",
            "--format=json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert not json.loads(result.stdout)


def prepare_audio(config):
    directory = config.work_dir / "job"
    directory.mkdir()
    source = directory / "source.webm"
    shutil.copyfile(Path(__file__).parent / "assets/audio-sample-chromium.webm", source)
    return directory, source


def test_real_conversion_probe_and_opus_validation(sandbox_config):
    directory, source = prepare_audio(sandbox_config)
    output = directory / "audio.ogg"
    with media_sandbox(sandbox_config, directory):
        assert _convert(source, output, 30) == pytest.approx(2.7165, abs=0.03)
        _validate_opus(output, 30)
    assert_no_sandboxes(sandbox_config)


def test_media_cannot_read_worker_files_or_reach_network(sandbox_config):
    directory, source = prepare_audio(sandbox_config)
    # These paths are embedded in media content, bypassing Python argv checks.
    outside = sandbox_config.work_dir / "private.webm"
    shutil.copyfile(source, outside)
    playlist = directory / "input.ffconcat"
    playlist.write_text(f"ffconcat version 1.0\nfile '{outside}'\n")
    with media_sandbox(sandbox_config, directory):
        with pytest.raises(ProcessingError, match="No such file"):
            _run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-safe",
                    "0",
                    "-i",
                    str(playlist),
                    "-f",
                    "null",
                    "/dev/null",
                ],
                15,
            )
        # A closed port would fail even without isolation; use a listening socket
        # and verify the sandbox cannot connect to it.
        with socket.socket() as server:
            server.bind(("0.0.0.0", 0))
            server.listen()
            server.settimeout(0.1)
            port = server.getsockname()[1]
            with pytest.raises(ProcessingError):
                _run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-i",
                        f"http://127.0.0.1:{port}/source",
                        "-f",
                        "null",
                        "/dev/null",
                    ],
                    5,
                )
            with pytest.raises(TimeoutError):
                server.accept()
    assert_no_sandboxes(sandbox_config)


def test_timeout_deletes_sandbox(sandbox_config):
    directory, source = prepare_audio(sandbox_config)
    started = time.monotonic()
    with media_sandbox(sandbox_config, directory):
        with pytest.raises(ProcessingError, match="timed out"):
            _run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-re",
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(source),
                    "-f",
                    "null",
                    "/dev/null",
                ],
                1,
            )
    assert time.monotonic() - started < 15
    assert_no_sandboxes(sandbox_config)


def test_supervisor_deletes_sandbox_after_killing_attempt(sandbox_config, task):
    directory, source = prepare_audio(sandbox_config)
    script = f"""
import json, pathlib, sys
from audio_extractor.settings import Settings
from audio_extractor.sandbox import media_sandbox
from audio_extractor.utils import _run
config = Settings.model_validate(json.load(sys.stdin)['settings'])
with media_sandbox(config, pathlib.Path({str(directory)!r})):
    _run(['ffmpeg', '-nostdin', '-re', '-stream_loop', '-1', '-i', {str(source)!r}, '-f', 'null', '/dev/null'], 60)
"""
    real_popen = subprocess.Popen

    def popen(command, **kwargs):
        if command == [sys.executable, "-m", "audio_extractor.attempt"]:
            command = [sys.executable, "-c", script]
        return real_popen(command, **kwargs)

    stop = threading.Event()
    running_pids = []

    def cancel_running_sandbox():
        while not stop.wait(0.05):
            state = subprocess.run(
                [
                    str(sandbox_config.runsc_path),
                    f"--root={sandbox_config.work_dir / '.gvisor'}",
                    "state",
                    "media",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if state.returncode == 0:
                payload = json.loads(state.stdout)
                if payload["status"] == "running":
                    running_pids.append(payload["pid"])
                    stop.set()

    observer = threading.Thread(target=cancel_running_sandbox)
    observer.start()
    try:
        with patch("audio_extractor.supervisor.subprocess.Popen", side_effect=popen):
            assert not _run_child(
                sandbox_config, task, time.monotonic() + 10, stop, HealthState(10)
            )
    finally:
        stop.set()
        observer.join()
    assert running_pids, "The attempt must reach a running sandbox before cancellation"
    assert_no_sandboxes(sandbox_config)
    try:
        state = Path(f"/proc/{running_pids[0]}/stat").read_text().split()[2]
    except FileNotFoundError, ProcessLookupError:
        state = None
    assert state in {None, "Z"}
