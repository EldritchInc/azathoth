"""The journal a run records while it executes, so it can be resumed (ADR 0105).

A run's journal is append-only and numbered from 1. It records, in the order
they happen:

- `run.started`: the workflow, its revision and the initial context;
- `attempt.started` and `attempt.finished`: each step attempt, the finished
  one with the whole `WorkflowStepAttempt`;
- `layer.committed`: each dependency layer once it commits, with its step
  runs, the events it added to the run's context, and the steps it blocked;
- `run.resumed`: each time another process resumed the run;
- `run.finished`: when and how the run ended.

The journal of a finished run holds everything its `WorkflowRun` does. The
recorded `WorkflowRun` itself is unchanged.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from azathoth.context import Context, ContextEvent
from azathoth.workflows.attempt import WorkflowStepAttempt
from azathoth.workflows.execution import WorkflowStepRun
from azathoth.workflows.models import WorkflowMetadata


class JournalRunStarted(BaseModel):
    """The run started: what it executes, and the context it starts from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["run.started"] = "run.started"
    workflow: WorkflowMetadata
    workflow_revision: int | None = Field(default=None, ge=1)
    initial_context: Context
    started_at: datetime


class JournalAttemptStarted(BaseModel):
    """One attempt of one step started."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["attempt.started"] = "attempt.started"
    step_id: UUID
    layer_index: int = Field(ge=0)
    attempt_number: int = Field(ge=1)
    started_at: datetime


class JournalAttemptFinished(BaseModel):
    """One attempt of one step finished, succeeding or failing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["attempt.finished"] = "attempt.finished"
    step_id: UUID
    layer_index: int = Field(ge=0)
    attempt: WorkflowStepAttempt


class JournalLayerCommitted(BaseModel):
    """One dependency layer committed.

    `steps` are the layer's step runs in declared order. `events` are the
    events the layer added to the run's context, in the order it added them.
    `blocked_step_ids` are every step blocked so far by a failure that skips
    its dependents, the layer's included.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["layer.committed"] = "layer.committed"
    layer_index: int = Field(ge=0)
    steps: tuple[WorkflowStepRun, ...]
    events: tuple[ContextEvent, ...] = ()
    blocked_step_ids: tuple[UUID, ...] = ()


class JournalRunResumed(BaseModel):
    """The run was resumed, by a process that found it unfinished."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["run.resumed"] = "run.resumed"
    resumed_at: datetime


class JournalRunFinished(BaseModel):
    """The run finished, halted or not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["run.finished"] = "run.finished"
    completed_at: datetime
    halted: bool
    halting_step_id: UUID | None = None


RunJournalEvent = Annotated[
    JournalRunStarted
    | JournalAttemptStarted
    | JournalAttemptFinished
    | JournalLayerCommitted
    | JournalRunResumed
    | JournalRunFinished,
    Field(discriminator="type"),
]
"""One event of a run's journal."""


class RunJournalEntry(BaseModel):
    """One numbered entry of one run's journal.

    `invocation_id` names the production invocation the run executes, on
    every entry of its journal, or is None for a run that executes none.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    position: int = Field(ge=1)
    workflow_id: UUID
    invocation_id: UUID | None = None
    recorded_at: datetime
    event: RunJournalEvent


class RunJournalError(RuntimeError):
    """A run's journal could not be recorded as it must be."""


class RunJournalPositionTakenError(RunJournalError):
    """Another entry already holds this position of the run's journal.

    Two processes recording the same run collide here, so the second never
    writes over the first.
    """

    def __init__(
        self,
        run_id: UUID,
        position: int,
    ) -> None:
        super().__init__(f"Run {run_id} already records journal position {position}.")
        self.run_id = run_id
        self.position = position


class RunJournalRepository(Protocol):
    """Persist the journals of runs, one append-only entry at a time."""

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        """Record one entry.

        Raises:
            RunJournalPositionTakenError: The run already records an entry
                at this position. Nothing is recorded.
        """

        ...

    def entries(
        self,
        run_id: UUID,
    ) -> tuple[RunJournalEntry, ...]:
        """Return every entry of one run's journal, in position order."""

        ...

    def invocation_run_id(
        self,
        invocation_id: UUID,
    ) -> UUID | None:
        """Return the run whose journal records this invocation, if one does."""

        ...


class InMemoryRunJournalRepository:
    """Keep run journals in memory, for tests and short-lived processes."""

    def __init__(
        self,
    ) -> None:
        self._entries: list[RunJournalEntry] = []

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        """Record one entry.

        Raises:
            RunJournalPositionTakenError: The run already records an entry
                at this position.
        """

        if any(
            existing.run_id == entry.run_id and existing.position == entry.position
            for existing in self._entries
        ):
            raise RunJournalPositionTakenError(entry.run_id, entry.position)

        self._entries.append(entry)

    def entries(
        self,
        run_id: UUID,
    ) -> tuple[RunJournalEntry, ...]:
        """Return every entry of one run's journal, in position order."""

        return tuple(
            sorted(
                (entry for entry in self._entries if entry.run_id == run_id),
                key=lambda entry: entry.position,
            )
        )

    def invocation_run_id(
        self,
        invocation_id: UUID,
    ) -> UUID | None:
        """Return the run whose journal records this invocation, if one does."""

        for entry in self._entries:
            if entry.invocation_id == invocation_id and entry.position == 1:
                return entry.run_id

        return None


Clock: TypeAlias = Callable[[], datetime]
"""Return the current time."""

Fence: TypeAlias = Callable[[], None]
"""Raise when this process may no longer write a run's journal."""


def _now() -> datetime:
    """Return the current time in UTC."""

    return datetime.now(UTC)


class RunJournalWriter:
    """Record one run's journal, numbering its entries in order.

    A writer given a fence calls it before every entry, so a process that no
    longer holds the run, such as one whose lease was taken over, stops
    before it writes another (ADR 0105).
    """

    def __init__(
        self,
        repository: RunJournalRepository,
        *,
        run_id: UUID,
        workflow_id: UUID,
        invocation_id: UUID | None = None,
        next_position: int = 1,
        clock: Clock | None = None,
        fence: Fence | None = None,
    ) -> None:
        if next_position < 1:
            raise ValueError("A run's journal is numbered from 1.")

        self._repository = repository
        self._run_id = run_id
        self._workflow_id = workflow_id
        self._invocation_id = invocation_id
        self._next_position = next_position
        self._clock: Clock = clock if clock is not None else _now
        self._fence = fence

    @property
    def run_id(
        self,
    ) -> UUID:
        """Return the run whose journal this writes."""

        return self._run_id

    @property
    def next_position(
        self,
    ) -> int:
        """Return the position the next entry takes."""

        return self._next_position

    def record(
        self,
        event: RunJournalEvent,
    ) -> RunJournalEntry:
        """Record one event at the next position, and return its entry.

        Raises:
            RunJournalPositionTakenError: Another process already recorded
                this position. The writer does not move on.
            RunJournalError: The fence refused, so nothing is recorded.
        """

        if self._fence is not None:
            self._fence()

        entry = RunJournalEntry(
            run_id=self._run_id,
            position=self._next_position,
            workflow_id=self._workflow_id,
            invocation_id=self._invocation_id,
            recorded_at=self._clock(),
            event=event,
        )

        self._repository.append(entry)
        self._next_position += 1

        return entry


def journaled_initial_context(
    journal: RunJournalRepository,
    run_id: UUID,
) -> Context | None:
    """Return the initial context one run's journal records it started from, or None.

    A run's journal begins with its start, which holds that context, whether
    the run is still under way or long finished (ADR 0114).
    """

    entries = journal.entries(run_id)

    if not entries or not isinstance(entries[0].event, JournalRunStarted):
        return None

    return entries[0].event.initial_context


__all__ = [
    "Clock",
    "Fence",
    "InMemoryRunJournalRepository",
    "JournalAttemptFinished",
    "JournalAttemptStarted",
    "JournalLayerCommitted",
    "JournalRunFinished",
    "JournalRunResumed",
    "JournalRunStarted",
    "RunJournalEntry",
    "RunJournalError",
    "RunJournalEvent",
    "RunJournalPositionTakenError",
    "RunJournalRepository",
    "RunJournalWriter",
    "journaled_initial_context",
]
