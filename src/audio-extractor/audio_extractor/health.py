"""Local health endpoints backed by supervisor progress, not dependencies."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class HealthState:
    """Small shared snapshot; probes never call the backend or storage."""

    def __init__(self, stale_after: float, drain_at: float = float("inf")):
        self.drain_at = drain_at
        self.initialized = False
        self.available = False
        self.draining = False
        self.heartbeat = time.monotonic()
        self.stale_after = stale_after
        self.lock = threading.Lock()

    def update(self, **values):
        """Publish state and a supervisor heartbeat atomically."""
        with self.lock:
            self.heartbeat = time.monotonic()
            for name, value in values.items():
                setattr(self, name, value)

    def status(self, path: str) -> int:
        """A busy or idle supervisor is healthy; draining is not ready."""
        with self.lock:
            live = time.monotonic() - self.heartbeat <= self.stale_after
            states = {
                "/startupz": self.initialized,
                "/livez": self.initialized and live,
                "/readyz": self.initialized
                and live
                and self.available
                and not self.draining
                and time.monotonic() < self.drain_at,
            }
            if path not in states:
                return 404
            return 200 if states[path] else 503


class HealthServer:
    """Serve probes directly on the Pod IP without a Kubernetes Service."""

    def __init__(self, state: HealthState, port: int):
        class Handler(BaseHTTPRequestHandler):
            """Return probe status without request logging."""

            def do_GET(self):  # pylint: disable=invalid-name
                """Serve a local lifecycle snapshot."""
                self.send_response(state.status(self.path))
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format, *args):  # pylint: disable=redefined-builtin
                """Suppress repetitive kubelet access logs."""

        self.server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
