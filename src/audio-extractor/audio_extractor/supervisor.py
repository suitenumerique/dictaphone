"""Recycle the container periodically and isolate every attempt in a child."""

import json
import logging
import os
import random
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests

from audio_extractor.api_models import TranscodingJob, ValidationJob
from audio_extractor.health import HealthServer, HealthState
from audio_extractor.http_client import close_session, configure_session, get_session
from audio_extractor.settings import Settings
from audio_extractor.utils import _clean_work_dir

LOGGER = logging.getLogger(__name__)


def _kill_attempt(process: subprocess.Popen) -> None:
    """Kill the isolated attempt's entire session, including media commands."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _run_child(config, job, deadline, stop, health, *, failure=False):  # noqa: PLR0913
    """Bound processing (including network retries) with an external deadline."""
    # pylint: disable=too-many-arguments
    values = config.model_dump(mode="json")
    values["token"] = config.token.get_secret_value()
    if config.sentry_dsn:
        values["sentry_dsn"] = config.sentry_dsn.get_secret_value()
    command = [sys.executable, "-m", "audio_extractor.attempt"]
    # Pass signed URLs and credentials over stdin, never command arguments.
    # Explicit cleanup kills the entire session before waiting for the child.
    # pylint: disable=consider-using-with
    process = subprocess.Popen(  # noqa: S603 - fixed Python module command
        command, stdin=subprocess.PIPE, text=True, start_new_session=True
    )
    try:
        process.stdin.write(
            json.dumps(
                {
                    "settings": values,
                    "job": job.model_dump(mode="json"),
                    "report_failure": failure,
                }
            )
        )
        process.stdin.close()
        while process.poll() is None:
            health.update(draining=stop.is_set() or time.monotonic() >= health.drain_at)
            if stop.is_set() or time.monotonic() >= deadline:
                return False
            stop.wait(min(0.25, max(0, deadline - time.monotonic())))
        return process.returncode == 0
    finally:
        # Also reap descendants left behind when their Python parent exits.
        _kill_attempt(process)


def _wait(seconds, stop, health):
    """Keep idle/retrying workers live even with long configured waits."""
    deadline = time.monotonic() + seconds
    while not stop.is_set() and time.monotonic() < deadline:
        health.update(draining=time.monotonic() >= health.drain_at)
        stop.wait(min(1, max(0, deadline - time.monotonic())))


def _process_attempt(config, job, claimed_at, stop, health):
    budget = config.job_timeout_seconds - (time.monotonic() - claimed_at)
    budget = min(budget, (job.expires_at - datetime.now(UTC)).total_seconds())
    deadline = time.monotonic() + max(0, budget)
    reserve = min(5, max(0, budget) / 10)
    LOGGER.info(
        "%s job %s started; budget_seconds=%.3f",
        config.mode,
        job.id,
        max(0, budget),
    )
    try:
        completed = False
        if budget > reserve and not stop.is_set():
            completed = _run_child(config, job, deadline - reserve, stop, health)
            LOGGER.info(
                "%s job %s processing %s",
                config.mode,
                job.id,
                "completed" if completed else "did not complete",
            )
        if not completed and not stop.is_set() and time.monotonic() < deadline:
            LOGGER.warning(
                "%s job %s did not complete; reporting failure",
                config.mode,
                job.id,
            )
            reported = _run_child(config, job, deadline, stop, health, failure=True)
            LOGGER.info(
                "%s job %s failure report %s",
                config.mode,
                job.id,
                "completed" if reported else "did not complete",
            )
    finally:
        _clean_work_dir(config.work_dir)
        LOGGER.info("%s job %s attempt finished", config.mode, job.id)


def _pull_job(config):
    response = get_session().get(
        urljoin(config.api_url + "/", f"audio-jobs/{config.mode}/next"),
        headers={"Authorization": f"Bearer {config.token.get_secret_value()}"},
        timeout=config.request_timeout,
    )
    response.raise_for_status()
    if response.status_code == 204:
        return None
    model = TranscodingJob if config.mode == "transcoding" else ValidationJob
    return model.model_validate(response.json())


def _install_signal_handlers(stop):
    old_handlers = {}

    def terminate(_signum, _frame):
        stop.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        old_handlers[signum] = signal.signal(signum, terminate)
    return old_handlers


def supervise(config: Settings) -> None:  # noqa: PLR0915
    """Poll until the lifetime deadline; drain normally, cancel on termination."""
    # pylint: disable=too-many-locals
    stop = threading.Event()
    deadline = time.monotonic() + config.max_runtime_seconds
    health = HealthState(stale_after=2 * config.request_timeout + 10, drain_at=deadline)
    started = time.monotonic()
    old_handlers = _install_signal_handlers(stop)
    handled = 0
    pull_attempts = 0
    polling_failures = 0
    retry_delay = 1.0
    reason = "fatal_error"
    try:
        _clean_work_dir(config.work_dir)
        configure_session(config)
        with HealthServer(health, config.health_port):
            health.update(initialized=True)
            while not stop.is_set() and time.monotonic() < deadline:
                health.update()
                claimed_at = time.monotonic()
                pull_attempts += 1
                if pull_attempts == 1 or pull_attempts % 5 == 0:
                    LOGGER.info(
                        "Pulling %s job (attempt %d; logged every 5 attempts)",
                        config.mode,
                        pull_attempts,
                    )
                try:
                    job = _pull_job(config)
                except (requests.RequestException, ValueError) as exc:
                    # Do not expose signed URLs or credentials from invalid responses.
                    polling_failures += 1
                    delay = min(30, retry_delay) * random.uniform(0.8, 1.2)  # noqa: S311
                    retry_delay = min(30, retry_delay * 2)
                    LOGGER.warning(
                        "Pull attempt %d failed (%s); retrying in %.1f seconds "
                        "(consecutive failures=%d)",
                        pull_attempts,
                        type(exc).__name__,
                        delay,
                        polling_failures,
                    )
                    health.update(available=False)
                    _wait(min(delay, max(0, deadline - time.monotonic())), stop, health)
                    continue
                retry_delay = 1.0
                polling_failures = 0
                health.update(
                    available=True,
                    draining=stop.is_set() or time.monotonic() >= deadline,
                )
                if job is None:
                    if pull_attempts == 1 or pull_attempts % 5 == 0:
                        LOGGER.info(
                            "Pull attempt %d found no %s job (logged every 5 attempts)",
                            pull_attempts,
                            config.mode,
                        )
                    _wait(
                        min(
                            config.poll_interval_seconds,
                            max(0, deadline - time.monotonic()),
                        ),
                        stop,
                        health,
                    )
                    continue
                LOGGER.info(
                    "Pull attempt %d claimed %s job %s",
                    pull_attempts,
                    config.mode,
                    job.id,
                )
                # A claim begun before the cutoff is honored even if it returns late.
                health.update(draining=time.monotonic() >= deadline)
                _process_attempt(config, job, claimed_at, stop, health)
                handled += 1
            health.update(draining=True)
        reason = "termination_requested" if stop.is_set() else "lifetime_reached"
    finally:
        close_session()
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        _clean_work_dir(config.work_dir)
        LOGGER.info(
            "Worker stopped: reason=%s uptime_seconds=%.3f tasks_handled=%d "
            "pull_attempts=%d polling_failures=%d",
            reason,
            time.monotonic() - started,
            handled,
            pull_attempts,
            polling_failures,
        )
