"""Health reflects local supervisor progress and draining state."""

import time
import urllib.error
import urllib.request

import pytest

from audio_extractor.health import HealthServer, HealthState


def test_health_states():
    health = HealthState(10)
    assert health.status("/startupz") == 503
    health.update(initialized=True, available=True)
    assert health.status("/startupz") == 200
    assert health.status("/livez") == 200
    assert health.status("/readyz") == 200
    health.update(available=False)
    assert health.status("/livez") == 200
    assert health.status("/readyz") == 503
    health.update(available=True, draining=True)
    assert health.status("/livez") == 200
    assert health.status("/readyz") == 503
    health.heartbeat = time.monotonic() - 11
    assert health.status("/livez") == 503
    assert health.status("/unknown") == 404


def test_readiness_expires_while_busy():
    health = HealthState(10, drain_at=time.monotonic() - 1)
    health.update(initialized=True, available=True)
    assert health.status("/readyz") == 503
    assert health.status("/livez") == 200


def test_http_probes():
    health = HealthState(10)
    with HealthServer(health, 0) as server:
        origin = f"http://127.0.0.1:{server.server.server_port}"
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(origin + "/startupz", timeout=2)
        assert error.value.code == 503
        health.update(initialized=True, available=True)
        with urllib.request.urlopen(origin + "/livez", timeout=2) as response:
            assert response.status == 200
            assert response.read() == b""
