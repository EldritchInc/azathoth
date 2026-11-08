"""Tests for progress notifications while an invocation runs (ADR 0111)."""

import asyncio
import threading
from uuid import UUID

import pytest

from azathoth import api
from azathoth_mcp.progress import StepProgress, progress_message

STEP_ID = UUID(int=1)


def finished() -> api.StepFinished:
    """Return one step's skipped finish."""

    return api.StepFinished(
        step_id=STEP_ID,
        layer=0,
        status="skipped",
        failure=None,
        confidence=None,
    )


def started() -> api.StepStarted:
    """Return one step's start."""

    return api.StepStarted(step_id=STEP_ID, layer=0, message=None)


def observe_all(
    total: int,
    *events: api.RunEvent,
) -> list[tuple[float, float | None, str | None]]:
    """Return the notifications some events, observed on a worker thread, send."""

    reports: list[tuple[float, float | None, str | None]] = []

    async def report(
        progress: float,
        of: float | None,
        message: str | None,
    ) -> None:
        reports.append((progress, of, message))

    async def run() -> None:
        progress = StepProgress(report, total=total, loop=asyncio.get_running_loop())

        def deliver() -> None:
            for event in events:
                progress.observe(event)

        await asyncio.to_thread(deliver)
        await progress.flush()

    asyncio.run(run())

    return reports


def test_each_finished_step_is_one_notification() -> None:
    assert observe_all(3, finished(), finished()) == [
        (1.0, 3.0, "1 of 3 steps finished."),
        (2.0, 3.0, "2 of 3 steps finished."),
    ]


def test_a_started_step_sends_nothing() -> None:
    assert observe_all(2, started(), finished(), started()) == [
        (1.0, 2.0, "1 of 2 steps finished."),
    ]


def test_progress_never_passes_its_total() -> None:
    assert observe_all(1, finished(), finished())[-1] == (1.0, 1.0, "1 of 1 steps finished.")


def test_a_run_counts_at_least_one_step() -> None:
    async def report(
        progress: float,
        of: float | None,
        message: str | None,
    ) -> None:
        return None

    loop = asyncio.new_event_loop()

    try:
        with pytest.raises(ValueError) as raised:
            StepProgress(report, total=0, loop=loop)
    finally:
        loop.close()

    assert str(raised.value) == "A run's progress counts at least one step."


def test_a_notification_that_fails_is_dropped() -> None:
    sent: list[float] = []

    async def report(
        progress: float,
        of: float | None,
        message: str | None,
    ) -> None:
        if progress == 1.0:
            raise ConnectionError("The client went away.")

        sent.append(progress)

    async def run() -> None:
        progress = StepProgress(report, total=2, loop=asyncio.get_running_loop())
        await asyncio.to_thread(progress.observe, finished())
        await asyncio.to_thread(progress.observe, finished())
        await progress.flush()

    asyncio.run(run())

    assert sent == [2.0]


def test_notifications_are_sent_on_the_calls_loop_not_the_observing_thread() -> None:
    threads: list[threading.Thread] = []

    async def report(
        progress: float,
        of: float | None,
        message: str | None,
    ) -> None:
        threads.append(threading.current_thread())

    async def run() -> threading.Thread:
        progress = StepProgress(report, total=1, loop=asyncio.get_running_loop())
        await asyncio.to_thread(progress.observe, finished())
        await progress.flush()

        return threading.current_thread()

    loop_thread = asyncio.run(run())

    assert threads == [loop_thread]


def test_the_message_counts_finished_steps() -> None:
    assert progress_message(2, 5) == "2 of 5 steps finished."
