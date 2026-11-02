"""Where a workflow run came from, recorded in its initial context (ADR 0104).

A run started by a step of another run is that step's child. Its initial
context holds one `workflow.lineage.received` event: how deeply it is nested,
the step that started it, and the run at the top of the tree. A run started
from outside Azathoth has no such event; it is a root, at depth 0, and records
exactly the context it always has.

While a step runs, the runner makes the step's lineage current, so that
anything the step starts as a child can learn where it was started from. The
engine, not a tool, bounds how deeply runs nest: a child beyond
`MAX_WORKFLOW_DEPTH` is refused.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from azathoth.context.models import Context, ContextEvent

LINEAGE_EVENT_TYPE = "workflow.lineage.received"
"""The event type of a child run's lineage in its initial context."""

LINEAGE_PRODUCER = "azathoth.lineage"
"""The producer of every lineage event."""

MAX_WORKFLOW_DEPTH = 8
"""The deepest a child run may be nested below its root run."""


class LineageError(ValueError):
    """Raised when recorded or supplied lineage is not valid lineage."""


class WorkflowDepthError(ValueError):
    """Raised when a child run would be nested beyond `MAX_WORKFLOW_DEPTH`."""


class LineageRun(BaseModel):
    """One run in a lineage: its workflow and the run's own ID."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    workflow_id: UUID
    run_id: UUID


class LineageStep(LineageRun):
    """One attempt of one step of a run: where a child run was started from."""

    step_id: UUID
    attempt: int = Field(ge=1)


class WorkflowLineage(BaseModel):
    """The lineage a child run records: its depth, its parent step and its root run."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    depth: int = Field(ge=1)
    parent: LineageStep
    root: LineageRun


class StepLineage(BaseModel):
    """What a running step tells a child about itself.

    `step` is the step's attempt, `depth` the depth of the run it belongs to,
    and `root` that run's root. A child run records them as its lineage, one
    level deeper.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    step: LineageStep
    depth: int = Field(ge=0)
    root: LineageRun


def child_lineage(
    step: StepLineage,
    *,
    workflow_id: UUID,
) -> WorkflowLineage:
    """Return the lineage of a child run of one workflow, started by one step.

    Raises:
        WorkflowDepthError: The child would be nested beyond `MAX_WORKFLOW_DEPTH`.
    """

    depth = step.depth + 1

    if depth > MAX_WORKFLOW_DEPTH:
        raise WorkflowDepthError(
            f"Workflow {workflow_id} would run at depth {depth}, "
            f"beyond the limit of {MAX_WORKFLOW_DEPTH} nested workflows."
        )

    return WorkflowLineage(
        depth=depth,
        parent=step.step,
        root=step.root,
    )


def create_lineage_event(
    lineage: WorkflowLineage,
    *,
    occurred_at: datetime | None = None,
) -> ContextEvent:
    """Create the event that records one child run's lineage."""

    return ContextEvent(
        event_type=LINEAGE_EVENT_TYPE,
        payload=lineage.model_dump(mode="json"),
        producer=LINEAGE_PRODUCER,
        occurred_at=occurred_at if occurred_at is not None else datetime.now(UTC),
    )


def lineage_of(
    context: Context,
) -> WorkflowLineage | None:
    """Return the lineage a context records, or `None` for a root run's context.

    Raises:
        LineageError: The context holds more than one lineage event, or one
            that is not valid lineage.
    """

    events = context.by_type(LINEAGE_EVENT_TYPE)

    if not events:
        return None

    if len(events) > 1:
        raise LineageError(f"A context records lineage once; this one has {len(events)} events.")

    try:
        return WorkflowLineage.model_validate(events[0].payload)
    except ValidationError as error:
        raise LineageError(
            f"The context's lineage is not valid lineage: {_first_problem(error)}."
        ) from error


class RunLineage(BaseModel):
    """One run's place in its lineage: the run, its depth and its root."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    run: LineageRun
    depth: int = Field(ge=0)
    root: LineageRun

    def step(
        self,
        *,
        step_id: UUID,
        attempt: int,
    ) -> StepLineage:
        """Return the lineage of one attempt of one of this run's steps."""

        return StepLineage(
            step=LineageStep(
                workflow_id=self.run.workflow_id,
                run_id=self.run.run_id,
                step_id=step_id,
                attempt=attempt,
            ),
            depth=self.depth,
            root=self.root,
        )


def run_lineage(
    context: Context,
    *,
    workflow_id: UUID,
    run_id: UUID,
) -> RunLineage:
    """Return the lineage of one run started with this initial context.

    A root run, whose context records no lineage, is its own root at depth 0.

    Raises:
        LineageError: The context's lineage is not valid lineage.
    """

    run = LineageRun(
        workflow_id=workflow_id,
        run_id=run_id,
    )

    lineage = lineage_of(context)

    if lineage is None:
        return RunLineage(run=run, depth=0, root=run)

    return RunLineage(run=run, depth=lineage.depth, root=lineage.root)


def encode_step_lineage(
    lineage: StepLineage,
) -> str:
    """Return one step's lineage as compact JSON, as a child process receives it."""

    return lineage.model_dump_json()


def decode_step_lineage(
    text: str,
) -> StepLineage:
    """Read one step's lineage from the JSON a child process received.

    Raises:
        LineageError: The text is not a step's lineage.
    """

    try:
        return StepLineage.model_validate_json(text)
    except ValidationError as error:
        raise LineageError(_first_problem(error)) from error


def _first_problem(
    error: ValidationError,
) -> str:
    """Describe the first problem pydantic found, briefly and without the value."""

    problem = error.errors(include_url=False, include_input=False)[0]
    location = ".".join(str(part) for part in problem["loc"])
    message = str(problem["msg"])

    return f"{location}: {message}" if location else message


_ACTIVE_STEP: ContextVar[StepLineage | None] = ContextVar(
    "azathoth_active_step_lineage",
    default=None,
)


def active_step_lineage() -> StepLineage | None:
    """Return the lineage of the step running in this context, if any."""

    return _ACTIVE_STEP.get()


@contextmanager
def running_step(
    lineage: StepLineage,
) -> Iterator[StepLineage]:
    """Make one step's lineage current for the work inside the block.

    The previous lineage is restored afterwards, so nested runs in one
    process each see their own steps.
    """

    token = _ACTIVE_STEP.set(lineage)

    try:
        yield lineage
    finally:
        _ACTIVE_STEP.reset(token)


__all__ = [
    "LINEAGE_EVENT_TYPE",
    "LINEAGE_PRODUCER",
    "MAX_WORKFLOW_DEPTH",
    "LineageError",
    "LineageRun",
    "LineageStep",
    "RunLineage",
    "StepLineage",
    "WorkflowDepthError",
    "WorkflowLineage",
    "active_step_lineage",
    "child_lineage",
    "create_lineage_event",
    "decode_step_lineage",
    "encode_step_lineage",
    "lineage_of",
    "run_lineage",
    "running_step",
]
