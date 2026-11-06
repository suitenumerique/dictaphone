"""Sandbox boundaries, failure behavior, and supervisor teardown."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from audio_extractor.health import HealthState
from audio_extractor.sandbox import (
    _spec,
    command_environment,
    media_sandbox,
    sandbox_command,
)
from audio_extractor.supervisor import _process_attempt, supervise
from audio_extractor.utils import ProcessingError, _run


def test_sandbox_exposes_only_job_and_rootfs(config, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_EXTRACTOR_TOKEN", "must-not-be-inherited")
    directory = tmp_path / "job"
    directory.mkdir()
    config = config.model_copy(update={"media_sandbox": "gvisor"})
    with (
        patch("audio_extractor.sandbox.cleanup_sandbox") as cleanup,
        media_sandbox(config, directory),
    ):
        with sandbox_command(["opusinfo", str(directory / "source.media")]) as command:
            spec = json.loads((Path(command[-2]) / "config.json").read_text())
            assert spec["root"] == {"path": "/opt/media-rootfs", "readonly": True}
            assert spec["process"]["args"] == ["/usr/bin/opusinfo", "/job/source.media"]
            assert spec["process"]["noNewPrivileges"]
            assert not any(spec["process"]["capabilities"].values())
            binds = [mount for mount in spec["mounts"] if mount["type"] == "bind"]
            assert [mount["source"] for mount in binds] == [str(directory)]
            assert "--network=none" in command
            assert "--ignore-cgroups=true" in command
            assert spec["linux"]["uidMappings"] == [
                {"containerID": 0, "hostID": os.geteuid(), "size": 1}
            ]
            assert "AUDIO_EXTRACTOR_TOKEN" not in command_environment()
            assert command_environment()["TMPDIR"] == str(config.work_dir)
        cleanup.assert_called_once_with(config)
    assert command_environment() is None


def test_sandbox_rejects_paths_outside_job_including_symlinks(config, tmp_path):
    directory = tmp_path / "job"
    directory.mkdir()
    (directory / "escape").symlink_to(tmp_path / "secret")
    for filename in (tmp_path / "secret", directory / "escape"):
        with pytest.raises(ValueError):
            _spec(config, directory, ["opusinfo", str(filename)])
    with pytest.raises(ValueError, match="Unsupported"):
        _spec(config, directory, ["sh", "-c", "true"])


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory", "hardlink"])
def test_sandbox_rejects_unsafe_files_before_worker_opens_them(config, tmp_path, kind):
    directory = tmp_path / "job"
    directory.mkdir()
    output = directory / "audio.ogg"
    config = config.model_copy(update={"media_sandbox": "gvisor"})
    with (
        patch("audio_extractor.sandbox.cleanup_sandbox"),
        media_sandbox(config, directory),
        pytest.raises(ValueError, match="unsafe job file"),
    ):
        with sandbox_command(["ffmpeg", "-version"]):
            if kind == "symlink":
                output.symlink_to("/etc/passwd")
            elif kind == "fifo":
                os.mkfifo(output)
            elif kind == "directory":
                output.mkdir()
            else:
                original = directory / "original"
                original.write_bytes(b"audio")
                output.hardlink_to(original)


@pytest.mark.parametrize(
    "failure", [OSError("not permitted"), subprocess.TimeoutExpired("runsc", 1)]
)
def test_sandbox_failure_never_falls_back_and_cleans_up(config, tmp_path, failure):
    config = config.model_copy(update={"media_sandbox": "gvisor"})
    with (
        media_sandbox(config, tmp_path),
        patch("audio_extractor.sandbox.cleanup_sandbox") as cleanup,
        patch("audio_extractor.utils.subprocess.run", side_effect=failure) as run,
        pytest.raises(ProcessingError),
    ):
        _run(["ffmpeg", "-version"], 1)
    assert run.call_count == 1
    assert run.call_args.args[0][0] == str(config.runsc_path)
    cleanup.assert_called_once_with(config)


def test_sandbox_startup_failure_prevents_claiming_jobs(lifecycle):
    config, _, _ = lifecycle
    config = config.model_copy(update={"media_sandbox": "gvisor"})
    with (
        patch("audio_extractor.supervisor.cleanup_sandbox"),
        patch("audio_extractor.supervisor._run", side_effect=ProcessingError("denied")),
        patch("audio_extractor.supervisor._pull_job") as claim,
        pytest.raises(ProcessingError, match="denied"),
    ):
        supervise(config)
    claim.assert_not_called()


def test_cleanup_failure_preserves_runtime_state(config, task, tmp_path):
    state = tmp_path / ".gvisor"
    state.mkdir()
    metadata = state / "runtime-state"
    metadata.write_text("needed to retry sandbox teardown")
    with (
        patch("audio_extractor.supervisor._run_child", return_value=True),
        patch(
            "audio_extractor.supervisor.cleanup_sandbox",
            side_effect=RuntimeError("cleanup failed"),
        ),
        pytest.raises(RuntimeError, match="cleanup failed"),
    ):
        _process_attempt(
            config, task, time.monotonic(), threading.Event(), HealthState(10)
        )
    assert metadata.exists()
