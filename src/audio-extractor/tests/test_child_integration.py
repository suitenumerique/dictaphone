"""Exercise actual child entry points against a local queue and storage stub."""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from audio_extractor.health import HealthServer, HealthState
from audio_extractor.supervisor import _run_child, supervise


class QueueHandler(BaseHTTPRequestHandler):
    def reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if hasattr(self.server, "claimed"):
            self.server.claimed.set()
        if self.path == "/source":
            self.reply(200, b"fake opus data")
        elif self.server.jobs:
            self.reply(200, json.dumps(self.server.jobs.pop(0)).encode())
        else:
            self.reply(204, b"")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.completions.append(json.loads(body))
        self.reply(200, b"{}")

    def log_message(self, format, *args):
        pass


def test_supervisor_runs_multiple_fresh_children_and_reports_results(
    config, tmp_path, monkeypatch
):
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("opusinfo", "opusdec"):
        command = tools / name
        command.write_text("#!/bin/sh\nexit 0\n")
        command.chmod(0o755)
    monkeypatch.setenv("PATH", str(tools))
    server = ThreadingHTTPServer(("127.0.0.1", 0), QueueHandler)
    origin = f"http://127.0.0.1:{server.server_port}"
    server.completions = []
    server.jobs = [
        {
            "id": f"job-{index}",
            "job_kind": "validation",
            "source_url": origin + "/source",
            "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
        }
        for index in range(2)
    ]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = config.model_copy(
        update={
            "api_url": origin,
            "mode": "validation",
            "work_dir": tmp_path / "work",
            "max_runtime_seconds": 2,
            "poll_interval_seconds": 0.01,
        }
    )
    try:
        with patch(
            "audio_extractor.supervisor.HealthServer",
            side_effect=lambda state, _port: HealthServer(state, 0),
        ):
            supervise(config)
        assert [result["id"] for result in server.completions] == ["job-0", "job-1"]
        assert all(result["status"] == "success" for result in server.completions)
        assert list(config.work_dir.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_failure_report_child_posts_attempt_failure(config, task):
    server = ThreadingHTTPServer(("127.0.0.1", 0), QueueHandler)
    server.completions = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = config.model_copy(
        update={"api_url": f"http://127.0.0.1:{server.server_port}"}
    )
    try:
        assert _run_child(
            config,
            task,
            time.monotonic() + 5,
            threading.Event(),
            HealthState(10),
            failure=True,
        )
        assert server.completions[0]["id"] == task.id
        assert server.completions[0]["status"] == "failure"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_wrapper_forwards_term_and_worker_cleans_up(config, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), QueueHandler)
    server.jobs = []
    server.claimed = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as socket_probe:
        socket_probe.bind(("127.0.0.1", 0))
        port = socket_probe.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{Path(sys.executable).parent}:{environment['PATH']}",
            "AUDIO_EXTRACTOR_API_URL": f"http://127.0.0.1:{server.server_port}",
            "AUDIO_EXTRACTOR_TOKEN": config.token.get_secret_value(),
            "AUDIO_EXTRACTOR_WORK_DIR": str(tmp_path / "work"),
            "AUDIO_EXTRACTOR_HEALTH_PORT": str(port),
            "AUDIO_EXTRACTOR_MAX_RUNTIME_SECONDS": "900",
            "AUDIO_EXTRACTOR_PROCESS_TIMEOUT_SECONDS": "1200",
            "AUDIO_EXTRACTOR_SHUTDOWN_GRACE_SECONDS": "30",
        }
    )
    command = Path(__file__).resolve().parents[1] / "run-worker.sh"
    process = subprocess.Popen(
        ["sh", str(command)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert server.claimed.wait(5)
        process.send_signal(signal.SIGTERM)
        _, logs = process.communicate(timeout=5)
        assert process.returncode in {0, 143}
        assert "reason=termination_requested" in logs
        assert list((tmp_path / "work").iterdir()) == []
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        server.shutdown()
        server.server_close()
        thread.join()
