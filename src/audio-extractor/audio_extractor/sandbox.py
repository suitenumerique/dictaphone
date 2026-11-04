"""Per-command gVisor sandboxes with an explicit, credential-free filesystem."""

import json
import os
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from audio_extractor.settings import Settings

MEDIA_TOOLS = frozenset({"ffmpeg", "ffprobe", "opusinfo", "opusdec"})
SANDBOX_ID = "media"
# Never pass worker credentials, signed URLs, or loader overrides to runsc.
COMMAND_ENV = {"PATH": os.defpath, "LANG": "C", "HOME": "/nonexistent"}
_ACTIVE: ContextVar[tuple["Settings", Path] | None] = ContextVar(
    "media_sandbox", default=None
)


def command_environment() -> dict[str, str] | None:
    """Keep runsc's temporary mounts on the container's writable work volume."""
    active = _ACTIVE.get()
    if active is not None and active[0].media_sandbox == "gvisor":
        return {**COMMAND_ENV, "TMPDIR": str(active[0].work_dir.resolve())}
    return None


def _runtime(config: "Settings") -> list[str]:
    return [
        str(config.runsc_path),
        f"--root={config.work_dir.resolve() / '.gvisor'}",
        "--platform=systrap",
        "--network=none",
        "--ignore-cgroups=true",
        "--directfs=false",
        "--host-settings=ignore",
    ]


def cleanup_sandbox(config: "Settings") -> None:
    """Delete even detached Sentry/gofer processes before deleting their state.

    The worker processes one command at a time, so its runtime has a single ID.
    `delete --force` also succeeds when that ID does not exist.
    """
    if config.media_sandbox != "gvisor":
        return
    subprocess.run(  # noqa: S603 - trusted runtime and fixed arguments
        [*_runtime(config), "delete", "--force", SANDBOX_ID],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env={**COMMAND_ENV, "TMPDIR": str(config.work_dir.resolve())},
        timeout=10,
    )


@contextmanager
def media_sandbox(config: "Settings", directory: Path):
    """Select the job directory to expose to media commands in this context."""
    token = _ACTIVE.set((config, directory.resolve()))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def _spec(config: "Settings", directory: Path, command: list[str]) -> dict:
    if command[0] not in MEDIA_TOOLS:
        raise ValueError(f"Unsupported sandbox media tool: {command[0]}")
    arguments = [f"/usr/bin/{command[0]}"]
    for argument in command[1:]:
        mapped = argument
        if argument.startswith("/") and argument != "/dev/null":
            # Resolve symlinks as well: no command may name an enclosing-worker file.
            relative = Path(argument).resolve().relative_to(directory)
            mapped = str(Path("/job") / relative)
        arguments.append(mapped)
    empty_capabilities = {
        name: []
        for name in ("bounding", "effective", "inheritable", "permitted", "ambient")
    }
    return {
        "ociVersion": "1.2.0",
        "root": {"path": str(config.sandbox_rootfs.resolve()), "readonly": True},
        "process": {
            "terminal": False,
            "user": {"uid": 0, "gid": 0},
            "args": arguments,
            "env": ["PATH=/usr/bin", "LANG=C", "HOME=/nonexistent", "TMPDIR=/tmp"],
            "cwd": "/job",
            "noNewPrivileges": True,
            "capabilities": empty_capabilities,
            "rlimits": [{"type": "RLIMIT_NOFILE", "hard": 1024, "soft": 1024}],
        },
        "mounts": [
            {"destination": "/proc", "type": "proc", "source": "proc"},
            {
                "destination": "/dev",
                "type": "tmpfs",
                "source": "tmpfs",
                "options": ["nosuid", "noexec", "mode=755", "size=1m"],
            },
            {
                "destination": "/tmp",  # noqa: S108 - sandbox-private tmpfs
                "type": "tmpfs",
                "source": "tmpfs",
                "options": ["nosuid", "nodev", "noexec", "mode=1777", "size=64m"],
            },
            {
                "destination": "/job",
                "type": "bind",
                "source": str(directory),
                "options": ["bind", "rw", "nosuid", "nodev", "noexec"],
            },
        ],
        "linux": {
            "namespaces": [
                {"type": name} for name in ("user", "pid", "mount", "ipc", "uts")
            ],
            # A single mapping avoids setuid helpers and /etc/subuid requirements.
            "uidMappings": [{"containerID": 0, "hostID": os.geteuid(), "size": 1}],
            "gidMappings": [{"containerID": 0, "hostID": os.getegid(), "size": 1}],
        },
    }


@contextmanager
def sandbox_command(command: list[str]):
    """Wrap a media command; always destroy its sandbox before draining stderr."""
    active = _ACTIVE.get()
    if active is None or active[0].media_sandbox == "none":
        yield command
        return
    config, directory = active
    config.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sandbox-", dir=config.work_dir) as bundle:
        spec = _spec(config, directory, command)
        (Path(bundle) / "config.json").write_text(json.dumps(spec))
        try:
            yield [*_runtime(config), "run", "--bundle", bundle, SANDBOX_ID]
        finally:
            cleanup_sandbox(config)
        # The worker opens these files outside the sandbox. Do not let a
        # compromised parser make it follow a symlink or block on a FIFO.
        for entry in directory.iterdir():
            attributes = entry.lstat()
            if not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1:
                raise ValueError("Media sandbox left an unsafe job file")
