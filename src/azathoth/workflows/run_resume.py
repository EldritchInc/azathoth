"""Reading a run's journal back: the run it finished as, or where to resume it (ADR 0105).

A run whose journal ends in `run.finished` is rebuilt whole by
`finished_run`. One that does not is resumed from its `RunResumePoint`:

- every layer it committed is kept as it was, its steps reused and the
  events it added replayed into the run's context;
- in the layer it was executing, each step's finished attempts are kept: a
  step whose last finished attempt succeeded is reused, and one whose
  attempts failed is retried from its next attempt number;
- an attempt that started but never finished is executed again, under the
  same number. Work in flight when the run stopped therefore runs at least
  once, and may run twice.

A journal that cannot be resumed with the given workflow is refused with a
`RunResumeError` that says why.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from azathoth.context import Context, ContextEvent
from azathoth.workflows.attempt import WorkflowStepAttempt
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.execution import WorkflowRun, WorkflowStepRun, WorkflowStepStatus
from azathoth.workflows.failure import WorkflowFailurePolicy
from azathoth.workflows.run_journal import (
    JournalAttemptFinished,
    JournalLayerCommitted,
    JournalRunFinished,
    JournalRunResumed,
    JournalRunStarted,
    RunJournalEntry,
)


class RunResumeError(RuntimeError):
    """A run cannot be resumed from its journal with the given workflow."""

    def __init__(
        self,
        run_id: UUID,
        message: str,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id


@dataclass(frozen=True)
class RunResumePoint:
    """Where an unfinished run resumes, and everything it keeps.

    `steps` and `context` are the run's committed steps and its context
    after the last committed layer. `next_layer` is the first layer not
    committed, and `attempts` the attempts its steps finished, by step.
    `halting_step_id` names the step a committed layer halted on, when the
    run stopped after that layer but before it finished.
    """

    run_id: UUID
    workflow_id: UUID
    invocation_id: UUID | None
    initial_context: Context
    started_at: datetime
    steps: tuple[WorkflowStepRun, ...]
    context: Context
    blocked_step_ids: frozenset[UUID]
    next_layer: int
    next_position: int
    attempts: Mapping[UUID, tuple[WorkflowStepAttempt, ...]] = field(default_factory=dict)
    halting_step_id: UUID | None = None


def _revision(
    revision: int | None,
) -> str:
    """Return a workflow revision as messages name it."""

    return "no revision" if revision is None else f"revision {revision}"


def _started(
    run_id: UUID,
    entries: Sequence[RunJournalEntry],
) -> JournalRunStarted:
    """Return the run's start, checking its journal is whole and numbered from 1.

    Raises:
        RunResumeError: The journal is empty, has a gap, or does not begin
            with the run's start.
    """

    if not entries:
        raise RunResumeError(run_id, f"Run {run_id} has no journal to resume.")

    for expected, entry in enumerate(entries, start=1):
        if entry.run_id != run_id:
            raise RunResumeError(run_id, f"Run {run_id}'s journal holds another run's entry.")

        if entry.position != expected:
            raise RunResumeError(run_id, f"Run {run_id}'s journal is missing position {expected}.")

    started = entries[0].event

    if not isinstance(started, JournalRunStarted):
        raise RunResumeError(run_id, f"Run {run_id}'s journal does not begin with run.started.")

    return started


def finished_run(
    entries: Sequence[RunJournalEntry],
) -> WorkflowRun | None:
    """Return the run a journal records as finished, rebuilt whole, or None if it is not.

    Raises:
        RunResumeError: The journal is not whole.
    """

    if not entries:
        return None

    run_id = entries[0].run_id
    started = _started(run_id, entries)
    finished = entries[-1].event

    if not isinstance(finished, JournalRunFinished):
        return None

    layers = [entry.event for entry in entries if isinstance(entry.event, JournalLayerCommitted)]

    events: list[ContextEvent] = [*started.initial_context.events]

    for layer in layers:
        events.extend(layer.events)

    return WorkflowRun(
        id=run_id,
        workflow=started.workflow,
        workflow_revision=started.workflow_revision,
        steps=tuple(step for layer in layers for step in layer.steps),
        initial_context=started.initial_context,
        final_context=started.initial_context.model_copy(update={"events": tuple(events)}),
        started_at=started.started_at,
        completed_at=finished.completed_at,
        halted=finished.halted,
        halting_step_id=finished.halting_step_id,
    )


def journal_resumes(
    entries: Sequence[RunJournalEntry],
) -> int:
    """Return how many times a run's journal records it was resumed."""

    return sum(1 for entry in entries if isinstance(entry.event, JournalRunResumed))


def resume_point(
    entries: Sequence[RunJournalEntry],
    *,
    run_id: UUID,
    workflow: WorkflowCandidate,
) -> RunResumePoint:
    """Return where an unfinished run resumes with the given workflow.

    Raises:
        RunResumeError: The journal is not whole, the run has finished, or
            the journal does not match the workflow: another workflow, another
            revision, or layers and steps the workflow does not have.
    """

    started = _started(run_id, entries)

    if isinstance(entries[-1].event, JournalRunFinished):
        raise RunResumeError(run_id, f"Run {run_id} has already finished.")

    workflow_id = workflow.metadata.id

    if started.workflow.id != workflow_id:
        raise RunResumeError(
            run_id,
            f"Run {run_id} executes workflow {started.workflow.id}, not workflow {workflow_id}.",
        )

    if started.workflow_revision != workflow.revision:
        raise RunResumeError(
            run_id,
            f"Run {run_id} started from {_revision(started.workflow_revision)} of workflow "
            f"{workflow_id}, not {_revision(workflow.revision)}.",
        )

    layers = workflow.execution_layers()
    policies = {step.id: step.failure_policy for step in workflow.steps}

    def mismatch(detail: str) -> RunResumeError:
        return RunResumeError(
            run_id,
            f"Run {run_id}'s journal does not match workflow {workflow_id}: {detail}.",
        )

    steps: list[WorkflowStepRun] = []
    events: list[ContextEvent] = [*started.initial_context.events]
    blocked: frozenset[UUID] = frozenset()
    next_layer = 0
    halting_step_id: UUID | None = None
    attempts: dict[UUID, list[WorkflowStepAttempt]] = {}

    for entry in entries[1:]:
        event = entry.event

        if isinstance(event, JournalLayerCommitted):
            if halting_step_id is not None:
                raise mismatch(f"layer {event.layer_index} commits after the run halted")

            if event.layer_index != next_layer:
                raise mismatch(f"layer {event.layer_index} commits before layer {next_layer}")

            if next_layer >= len(layers):
                raise mismatch(f"layer {event.layer_index} is not one of its layers")

            declared = tuple(step.id for step in layers[next_layer])

            if tuple(step.step_id for step in event.steps) != declared:
                raise mismatch(f"layer {event.layer_index} commits other steps")

            steps.extend(event.steps)
            events.extend(event.events)
            blocked = frozenset(event.blocked_step_ids)

            for step in event.steps:
                if (
                    step.status is WorkflowStepStatus.FAILED
                    and policies[step.step_id] is WorkflowFailurePolicy.FAIL_WORKFLOW
                ):
                    halting_step_id = step.step_id
                    break

            next_layer += 1
            attempts = {}

            continue

        if isinstance(event, JournalAttemptFinished):
            if event.layer_index != next_layer:
                raise mismatch(
                    f"step {event.step_id} finishes an attempt in layer {event.layer_index}, "
                    f"not layer {next_layer}"
                )

            if next_layer >= len(layers) or event.step_id not in {
                step.id for step in layers[next_layer]
            }:
                raise mismatch(f"step {event.step_id} is not in layer {next_layer}")

            finished = attempts.setdefault(event.step_id, [])

            if event.attempt.attempt_number != len(finished) + 1:
                raise mismatch(
                    f"step {event.step_id} finishes attempt {event.attempt.attempt_number} "
                    "out of order"
                )

            finished.append(event.attempt)

    return RunResumePoint(
        run_id=run_id,
        workflow_id=workflow_id,
        invocation_id=entries[0].invocation_id,
        initial_context=started.initial_context,
        started_at=started.started_at,
        steps=tuple(steps),
        context=started.initial_context.model_copy(update={"events": tuple(events)}),
        blocked_step_ids=blocked,
        next_layer=next_layer,
        next_position=len(entries) + 1,
        attempts={step_id: tuple(finished) for step_id, finished in attempts.items()},
        halting_step_id=halting_step_id,
    )


__all__ = [
    "RunResumeError",
    "RunResumePoint",
    "finished_run",
    "journal_resumes",
    "resume_point",
]
