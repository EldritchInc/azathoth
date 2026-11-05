"""Tests for progress notifications while an invocation runs (ADR 0111)."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.workflows import (
    WorkflowCandidateStep,
    WorkflowStepFinished,
    WorkflowStepStarted,
    WorkflowStepStatus,
)
from azathoth_mcp.progress import StepProgress, progress_message


class StaticStrategy:
    """A strategy that is never run; the events only name it."""

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return StrategyMetadata(
            id=UUID(int=2),
            name="progress-step",
            description="Exercise progress.",
        )

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Return a fixed outcome."""

        return StrategyOutcome(output="success")


def candidate_step() -> WorkflowCandidateStep:
    """Return one step as the runner reports it."""

    return WorkflowCandidateStep(id=UUID(int=1), strategy=StaticStrategy())


def finished() -> WorkflowStepFinished:
    """Return one step's skipped finish."""

    return WorkflowStepFinished(
        step=candidate_step(),
        layer_index=0,
        status=WorkflowStepStatus.SKIPPED,
    )


def observe_all(
    total: int,
    *events: WorkflowStepFinished | WorkflowStepStarted,
) -> list[tuple[float, float | None, str | None]]:
    """Return the notifications a run of some events sends."""

    reports: list[tuple[float, float | None, str | None]] = []

    async def report(
        progress: float,
        of: float | None,
        message: str | None,
    ) -> None:
        reports.append((progress, of, message))

    async def run() -> None:
        progress = StepProgress(report, total=total)

        for event in events:
            progress.observe(event)

        await progress.flush()

    asyncio.run(run())

    return reports


def test_each_finished_step_is_one_notification() -> None:
    assert observe_all(3, finished(), finished()) == [
        (1.0, 3.0, "1 of 3 steps finished."),
        (2.0, 3.0, "2 of 3 steps finished."),
    ]


def test_a_started_step_sends_nothing() -> None:
    started = WorkflowStepStarted(step=candidate_step(), layer_index=0)

    assert observe_all(2, started, finished(), started) == [
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

    with pytest.raises(ValueError) as raised:
        StepProgress(report, total=0)

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
        progress = StepProgress(report, total=2)
        progress.observe(finished())
        progress.observe(finished())
        await progress.flush()

    asyncio.run(run())

    assert sent == [2.0]


def test_the_message_counts_finished_steps() -> None:
    assert progress_message(2, 5) == "2 of 5 steps finished."
