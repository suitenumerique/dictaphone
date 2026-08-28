"""Tests for the AI-service capacity and queue estimator."""

from datetime import datetime, timedelta, timezone

from core.capacity_estimator import Task, estimate_tasks_eta


def test_estimate_tasks_eta_returns_each_unfinished_task_in_fcfs_order():
    """One queue reconstruction should provide ETAs for all pending tasks."""
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    tasks = [
        Task(
            id="completed",
            created_at=now - timedelta(minutes=2),
            weight=33,
            done_at=now - timedelta(minutes=1),
        ),
        Task(
            id="active",
            created_at=now - timedelta(seconds=5),
            weight=330,
        ),
        Task(
            id="queued-first",
            created_at=now - timedelta(seconds=4),
            weight=66,
        ),
        Task(
            id="queued-second",
            created_at=now - timedelta(seconds=3),
            weight=33,
        ),
    ]

    estimates = estimate_tasks_eta(tasks, C=33, now=now)

    assert set(estimates) == {"active", "queued-first", "queued-second"}
    assert estimates["active"].eta == now + timedelta(seconds=5)
    assert estimates["queued-first"].predicted_start_at == now + timedelta(seconds=5)
    assert estimates["queued-first"].eta == now + timedelta(seconds=7)
    assert estimates["queued-second"].predicted_start_at == now + timedelta(seconds=7)
    assert estimates["queued-second"].eta == now + timedelta(seconds=8)


def test_estimate_tasks_eta_returns_no_estimates_without_pending_tasks():
    """Completed tasks do not receive a delivery estimate."""
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    tasks = [
        Task(
            id="completed",
            created_at=now - timedelta(minutes=2),
            weight=33,
            done_at=now - timedelta(minutes=1),
        )
    ]

    assert not estimate_tasks_eta(tasks, now=now)


def test_estimate_tasks_eta_uses_parallel_capacity_for_queued_tasks():
    """Queued work starts when the first of several workers becomes available."""
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    tasks = [
        Task(id="active-first", created_at=now - timedelta(seconds=2), weight=330),
        Task(id="active-second", created_at=now - timedelta(seconds=1), weight=330),
        Task(id="queued", created_at=now, weight=33),
    ]

    estimates = estimate_tasks_eta(tasks, C=33, now=now, default_capacity=2)

    assert estimates["active-first"].eta == now + timedelta(seconds=8)
    assert estimates["active-second"].eta == now + timedelta(seconds=9)
    assert estimates["queued"].predicted_start_at == now + timedelta(seconds=8)
    assert estimates["queued"].eta == now + timedelta(seconds=9)


def test_estimate_tasks_eta_excludes_tasks_not_submitted_yet():
    """A future task must not be presented as queued work."""
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    tasks = [
        Task(id="submitted", created_at=now - timedelta(seconds=1), weight=33),
        Task(id="future", created_at=now + timedelta(seconds=1), weight=33),
    ]

    estimates = estimate_tasks_eta(tasks, C=33, now=now)

    assert set(estimates) == {"submitted"}
