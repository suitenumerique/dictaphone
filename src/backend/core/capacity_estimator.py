"""Estimate shared-service capacity and task delivery times."""

# The estimator exposes its tuning parameters and carries the intermediate
# diagnostics needed to explain an ETA to callers.
# pylint: disable=invalid-name,too-many-arguments,too-many-locals
# pylint: disable=too-many-branches,too-many-statements,too-many-instance-attributes

from __future__ import annotations

import heapq
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """A submitted unit of work, optionally with its completion timestamp."""

    id: str
    created_at: datetime
    weight: float
    done_at: Optional[datetime] = None

    @property
    def is_done(self) -> bool:
        """Whether the task has completed."""
        return self.done_at is not None


@dataclass(frozen=True)
class CapacityWindow:
    """Capacity and queue-observation metrics for a time window."""

    start: datetime
    end: datetime

    completed_tasks: int

    # Sum(d / C) of tasks completed in this window.
    completed_work_s: float

    # Equivalent fully-busy workers observed during the window.
    throughput_workers: float

    # Average number of submitted/not-done tasks in the system.
    avg_system_size: float

    # Fraction of the window for which the system appeared backlogged.
    high_load_fraction: float

    # Whether we trust this window as an observation of actual capacity.
    saturated: bool

    # Recency weight.
    weight: float


@dataclass(frozen=True)
class CapacityEstimate:
    """The inferred effective service capacity and supporting observations."""

    # Continuous estimate, e.g. 4.82 equivalent workers.
    effective_workers: float

    # Discrete worker count used by the queue simulator.
    worker_count: int

    confidence: str

    saturated_windows: int

    newest_saturated_window_end: Optional[datetime]

    windows: tuple[CapacityWindow, ...]


@dataclass(frozen=True)
class QueueState:
    """The inferred current division between active and queued tasks."""

    # Submitted tasks inferred to currently occupy workers.
    active: tuple[Task, ...]

    # Submitted tasks inferred to be waiting.
    queued: tuple[Task, ...]

    # Inferred start time for active/recent tasks.
    inferred_started_at: dict[str, datetime]

    # Where reconstruction started.
    anchor: datetime


@dataclass(frozen=True)
class EtaEstimate:
    """The predicted delivery time and reconstruction used for one task."""

    task_id: str

    eta: datetime
    seconds_from_now: float

    predicted_start_at: datetime

    capacity: CapacityEstimate
    queue_state: QueueState


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def service_seconds(task: Task, C: float) -> float:
    """
    Nominal amount of one-worker processing time required by a task.

    With:
        d = 3000
        C = 33

    this gives ~90.9 seconds.
    """
    if C <= 0:
        raise ValueError("C must be > 0")

    return task.weight / C


def _validate(
    tasks: Sequence[Task],
    now: datetime,
    C: float,
) -> None:
    if C <= 0:
        raise ValueError("C must be > 0")

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    ids = set()

    for task in tasks:
        if task.id in ids:
            raise ValueError(f"Duplicate task id: {task.id}")

        ids.add(task.id)

        if task.weight < 0:
            raise ValueError(f"{task.id}: d must be >= 0")

        if task.created_at.tzinfo is None or task.created_at.utcoffset() is None:
            raise ValueError(f"{task.id}: created_at must be timezone-aware")

        if task.done_at is not None:
            if task.done_at.tzinfo is None or task.done_at.utcoffset() is None:
                raise ValueError(f"{task.id}: done_at must be timezone-aware")

            if task.done_at < task.created_at:
                raise ValueError(f"{task.id}: done_at is before created_at")


def _weighted_median(
    values: list[tuple[float, float]],
) -> float:
    """
    values = [(value, weight), ...]
    """
    values = sorted(values)

    total_weight = sum(weight for _, weight in values)

    if total_weight <= 0:
        return statistics.median(value for value, _ in values)

    current = 0.0

    for value, weight in values:
        current += weight

        if current >= total_weight / 2:
            return value

    return values[-1][0]


# ---------------------------------------------------------------------------
# Queue occupancy
# ---------------------------------------------------------------------------


def _occupancy_segments(
    tasks: Sequence[Task],
    start: datetime,
    end: datetime,
):
    """
    Yield:

        (duration_seconds, number_of_tasks_in_system)

    for each constant-occupancy segment inside [start, end].

    A task is considered in the system for:

        created_at <= t < done_at

    or indefinitely if done_at is None.
    """

    events: dict[datetime, int] = {}

    initial = 0

    for task in tasks:
        alive_end = task.done_at or end

        if task.created_at < start < alive_end:
            initial += 1

        a = max(task.created_at, start)
        b = min(alive_end, end)

        if a >= b:
            continue

        if a > start:
            events[a] = events.get(a, 0) + 1
        elif task.created_at == start:
            events[a] = events.get(a, 0) + 1

        events[b] = events.get(b, 0) - 1

    n = initial
    previous = start

    for timestamp in sorted(events):
        if timestamp > previous:
            yield (
                (timestamp - previous).total_seconds(),
                n,
            )

        n += events[timestamp]
        previous = timestamp

    if previous < end:
        yield (
            (end - previous).total_seconds(),
            n,
        )


# ---------------------------------------------------------------------------
# Capacity estimation
# ---------------------------------------------------------------------------


def estimate_capacity(  # noqa: PLR0913, PLR0912, PLR0915
    tasks: Sequence[Task],
    *,
    C: float,
    now: Optional[datetime] = None,
    # How far into history to inspect.
    lookback: timedelta = timedelta(hours=2),
    # Throughput measurement window.
    window: timedelta = timedelta(minutes=10),
    # Sliding-window step.
    step: timedelta = timedelta(minutes=2),
    # How quickly old capacity measurements lose relevance.
    half_life: timedelta = timedelta(minutes=30),
    # Avoid drawing conclusions from tiny samples.
    min_completed_tasks: int = 3,
    # Require some actual queueing before calling a window saturated.
    backlog_margin: float = 0.75,
    # System must look backlogged for at least this fraction of the window.
    min_high_load_fraction: float = 0.50,
    # Used if no saturated period exists in the lookback.
    default_capacity: Optional[float] = None,
) -> CapacityEstimate:
    """
    Estimate the recent effective number of parallel workers.

    Crucially:

        observed throughput != capacity

    unless the system was saturated.

    For each rolling window we calculate:

        throughput_workers =
            sum(d / C for completed tasks) / window_duration

    Then we only trust it as a capacity observation if the queue occupancy
    suggests there was enough demand to keep the workers busy.
    """

    tasks = list(tasks)

    if now is None:
        now = datetime.now(timezone.utc)

    _validate(tasks, now, C)

    if window <= timedelta(0):
        raise ValueError("window must be > 0")

    if step <= timedelta(0):
        raise ValueError("step must be > 0")

    if lookback < window:
        raise ValueError("lookback must be >= window")

    windows: list[CapacityWindow] = []

    end = now
    earliest_end = now - lookback + window

    while end >= earliest_end:
        start = end - window

        duration_s = (end - start).total_seconds()

        completed = [
            task
            for task in tasks
            if (task.done_at is not None and start < task.done_at <= end)
        ]

        completed_work_s = sum(service_seconds(task, C) for task in completed)

        throughput_workers = completed_work_s / duration_s

        occupancy = list(
            _occupancy_segments(
                tasks,
                start,
                end,
            )
        )

        avg_system_size = sum(seconds * n for seconds, n in occupancy) / duration_s

        # Example:
        #
        # observed throughput ~= 4 workers
        #
        # If N(t) >= 5 for much of the window, there is evidence
        # that workers were actually saturated rather than merely
        # processing the available demand.
        high_load_threshold = max(
            1,
            math.ceil(throughput_workers) + 1,
        )

        high_load_seconds = sum(
            seconds for seconds, n in occupancy if n >= high_load_threshold
        )

        high_load_fraction = high_load_seconds / duration_s

        saturated = (
            len(completed) >= min_completed_tasks
            and throughput_workers > 0
            and (avg_system_size >= throughput_workers + backlog_margin)
            and (high_load_fraction >= min_high_load_fraction)
        )

        age_s = (now - end).total_seconds()

        half_life_s = max(
            1.0,
            half_life.total_seconds(),
        )

        weight = math.exp(-math.log(2) * age_s / half_life_s)

        windows.append(
            CapacityWindow(
                start=start,
                end=end,
                completed_tasks=len(completed),
                completed_work_s=completed_work_s,
                throughput_workers=throughput_workers,
                avg_system_size=avg_system_size,
                high_load_fraction=high_load_fraction,
                saturated=saturated,
                weight=weight,
            )
        )

        end -= step

    saturated_windows = [w for w in windows if w.saturated]

    if saturated_windows:
        # Robust against one weird/bursty window.
        effective_workers = _weighted_median(
            [
                (
                    w.throughput_workers,
                    w.weight,
                )
                for w in saturated_windows
            ]
        )

        newest_saturated = max(w.end for w in saturated_windows)

        age = now - newest_saturated

        if len(saturated_windows) >= 3 and age <= 2 * step:
            confidence = "high"

        elif age <= half_life:
            confidence = "medium"

        else:
            confidence = "low"

    else:
        newest_saturated = None

        usable = [
            w
            for w in windows
            if (w.completed_tasks >= min_completed_tasks and w.throughput_workers > 0)
        ]

        if default_capacity is not None:
            effective_workers = float(default_capacity)

            confidence = "fallback"

        elif usable:
            # No saturation means throughput only provides a lower
            # bound on capacity.
            #
            # Use the highest observed throughput rather than the
            # latest one so idle periods do not drag capacity down.
            effective_workers = max(w.throughput_workers for w in usable)

            confidence = "low"

        else:
            effective_workers = 1.0
            confidence = "low"

    effective_workers = max(
        effective_workers,
        1e-6,
    )

    worker_count = max(
        1,
        round(effective_workers),
    )

    return CapacityEstimate(
        effective_workers=effective_workers,
        worker_count=worker_count,
        confidence=confidence,
        saturated_windows=len(saturated_windows),
        newest_saturated_window_end=(newest_saturated),
        windows=tuple(windows),
    )


# ---------------------------------------------------------------------------
# Current queue reconstruction
# ---------------------------------------------------------------------------


def _latest_empty_time(
    tasks: Sequence[Task],
    now: datetime,
    not_before: datetime,
) -> Optional[datetime]:
    """
    Find the most recent timestamp at which the real observed system
    contained zero tasks.

    This gives us an excellent queue-reconstruction anchor because at
    that point every worker is known to have been idle.
    """

    n = sum(
        1
        for task in tasks
        if (
            task.created_at < not_before
            and (task.done_at is None or task.done_at >= not_before)
        )
    )

    # timestamp -> [completions, arrivals]
    events: dict[
        datetime,
        list[int],
    ] = {}

    for task in tasks:
        if not_before <= task.created_at <= now:
            events.setdefault(
                task.created_at,
                [0, 0],
            )[1] += 1

        if task.done_at is not None and not_before <= task.done_at <= now:
            events.setdefault(
                task.done_at,
                [0, 0],
            )[0] += 1

    latest = not_before if n == 0 else None

    for timestamp in sorted(events):
        completions, arrivals = events[timestamp]

        n -= completions
        n += arrivals

        if n == 0:
            latest = timestamp

    return latest


def infer_current_queue(
    tasks: Sequence[Task],
    *,
    C: float,
    worker_count: int,
    now: datetime,
    # We don't need to replay arbitrarily old history if the queue
    # has been non-empty forever.
    replay_horizon: timedelta = timedelta(minutes=30),
) -> QueueState:
    """
    Infer which submitted tasks are active vs waiting.

    We don't observe task start times directly.

    Instead we replay:

        task arrivals
        actual task completions

    under FCFS and the estimated number of workers.

    If capacity has been stable over the replay interval, this provides
    a good reconstruction of current worker occupancy.
    """

    if worker_count < 1:
        raise ValueError("worker_count must be >= 1")

    visible = [task for task in tasks if task.created_at <= now]

    not_before = now - replay_horizon

    empty = _latest_empty_time(
        visible,
        now,
        not_before,
    )

    anchor = empty if empty is not None else not_before

    alive_at_anchor = sorted(
        [
            task
            for task in visible
            if (
                task.created_at <= anchor
                and (task.done_at is None or task.done_at > anchor)
            )
        ],
        key=lambda task: (
            task.created_at,
            task.id,
        ),
    )

    active: dict[str, Task] = {}

    inferred_started_at: dict[
        str,
        datetime,
    ] = {}

    waiting: list[tuple[datetime, str, Task]] = []

    # If the system wasn't empty at our arbitrary anchor,
    # the oldest min(M, N) jobs are the best FCFS estimate
    # for which jobs were active.
    for i, task in enumerate(alive_at_anchor):
        if i < worker_count:
            active[task.id] = task

            # We don't know exactly when these initial tasks
            # started. This is only relevant until they finish.
            inferred_started_at[task.id] = max(
                task.created_at,
                anchor
                - timedelta(
                    seconds=service_seconds(
                        task,
                        C,
                    )
                ),
            )

        else:
            heapq.heappush(
                waiting,
                (
                    task.created_at,
                    task.id,
                    task,
                ),
            )

    # 0 = completion
    # 1 = arrival
    #
    # so completion events at the same timestamp happen first.
    events: list[tuple[datetime, int, Task]] = []

    for task in visible:
        if anchor < task.created_at <= now:
            events.append(
                (
                    task.created_at,
                    1,
                    task,
                )
            )

        if task.done_at is not None and anchor < task.done_at <= now:
            events.append(
                (
                    task.done_at,
                    0,
                    task,
                )
            )

    events.sort(
        key=lambda event: (
            event[0],
            event[1],
            event[2].id,
        )
    )

    def fill_workers(
        timestamp: datetime,
    ) -> None:
        while len(active) < worker_count and waiting:
            _, _, task = heapq.heappop(waiting)

            active[task.id] = task

            inferred_started_at[task.id] = timestamp

    for timestamp, event_type, task in events:
        if event_type == 0:
            # Actual completion.
            active.pop(task.id, None)

            # Capacity may have changed during the replay period,
            # so reconstruction can occasionally disagree.
            waiting = [item for item in waiting if item[2].id != task.id]

            heapq.heapify(waiting)

            fill_workers(timestamp)

        else:
            heapq.heappush(
                waiting,
                (
                    task.created_at,
                    task.id,
                    task,
                ),
            )

            fill_workers(timestamp)

    fill_workers(now)

    # Never expose completed jobs as current state.
    active = {task_id: task for task_id, task in active.items() if task.done_at is None}

    waiting = [item for item in waiting if item[2].done_at is None]

    heapq.heapify(waiting)

    return QueueState(
        active=tuple(
            sorted(
                active.values(),
                key=lambda task: (
                    task.created_at,
                    task.id,
                ),
            )
        ),
        queued=tuple(item[2] for item in sorted(waiting)),
        inferred_started_at=(inferred_started_at),
        anchor=anchor,
    )


# ---------------------------------------------------------------------------
# ETA
# ---------------------------------------------------------------------------


def estimate_tasks_eta(  # noqa: PLR0913
    tasks: Sequence[Task],
    *,
    C: float = 33.0,
    now: Optional[datetime] = None,
    # Very useful if you know your usual/minimum worker count.
    default_capacity: Optional[float] = None,
    capacity_lookback: timedelta = timedelta(hours=2),
    capacity_window: timedelta = timedelta(minutes=10),
    capacity_step: timedelta = timedelta(minutes=2),
    capacity_half_life: timedelta = timedelta(minutes=30),
    replay_horizon: timedelta = timedelta(minutes=30),
) -> dict[str, EtaEstimate]:
    """
    Estimate completion timestamps for all submitted, unfinished tasks.

    Capacity estimation and queue reconstruction are performed once for the
    whole batch.
    """

    tasks = list(tasks)

    if now is None:
        now = datetime.now(timezone.utc)

    _validate(tasks, now, C)

    capacity = estimate_capacity(
        tasks,
        C=C,
        now=now,
        lookback=capacity_lookback,
        window=capacity_window,
        step=capacity_step,
        half_life=capacity_half_life,
        default_capacity=default_capacity,
    )

    queue_state = infer_current_queue(
        tasks,
        C=C,
        worker_count=capacity.worker_count,
        now=now,
        replay_horizon=replay_horizon,
    )

    # ------------------------------------------------------------
    # Reconstruct current worker availability
    # ------------------------------------------------------------

    worker_available: list[datetime] = []

    for task in queue_state.active:
        started_at = queue_state.inferred_started_at.get(
            task.id,
            now,
        )

        elapsed_s = max(
            0.0,
            (now - started_at).total_seconds(),
        )

        remaining_s = max(
            0.0,
            service_seconds(
                task,
                C,
            )
            - elapsed_s,
        )

        heapq.heappush(
            worker_available,
            now + timedelta(seconds=remaining_s),
        )

    # Idle workers are available immediately.
    while len(worker_available) < capacity.worker_count:
        heapq.heappush(
            worker_available,
            now,
        )

    estimates = {}
    for task in queue_state.active:
        started_at = queue_state.inferred_started_at.get(
            task.id,
            now,
        )

        elapsed_s = max(
            0.0,
            (now - started_at).total_seconds(),
        )

        remaining_s = max(
            0.0,
            service_seconds(
                task,
                C,
            )
            - elapsed_s,
        )

        eta = now + timedelta(seconds=remaining_s)

        estimates[task.id] = EtaEstimate(
            task_id=task.id,
            eta=eta,
            seconds_from_now=(eta - now).total_seconds(),
            predicted_start_at=started_at,
            capacity=capacity,
            queue_state=queue_state,
        )

    # ------------------------------------------------------------
    # Queued tasks: FCFS forward simulation
    # ------------------------------------------------------------

    queued = list(queue_state.queued)
    unfinished_tasks = [
        task for task in tasks if task.done_at is None and task.created_at <= now
    ]

    pending_ids = {task.id for task in queue_state.active} | {
        task.id for task in queued
    }

    # Defensive fallback in case queue reconstruction was imperfect.
    queued.extend(task for task in unfinished_tasks if task.id not in pending_ids)

    queued.sort(
        key=lambda task: (
            task.created_at,
            task.id,
        )
    )

    for task in queued:
        worker_free_at = heapq.heappop(worker_available)

        start_at = max(
            now,
            worker_free_at,
        )

        finish_at = start_at + timedelta(
            seconds=service_seconds(
                task,
                C,
            )
        )

        heapq.heappush(
            worker_available,
            finish_at,
        )

        estimates[task.id] = EtaEstimate(
            task_id=task.id,
            eta=finish_at,
            seconds_from_now=(finish_at - now).total_seconds(),
            predicted_start_at=start_at,
            capacity=capacity,
            queue_state=queue_state,
        )

    return estimates
