"""Tests that the runner gives every step attempt its lineage (ADR 0104)."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import (
    Context,
    ContextEvent,
    LineageError,
    LineageRun,
    LineageStep,
    StepLineage,
    active_step_lineage,
    child_lineage,
    create_lineage_event,
)
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRunner,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("50000000-0000-4000-8000-000000000001")
FIRST_STEP_ID = UUID("50000000-0000-4000-8000-000000000011")
SECOND_STEP_ID = UUID("50000000-0000-4000-8000-000000000012")
LATER_STEP_ID = UUID("50000000-0000-4000-8000-000000000013")
STRATEGY_ID = UUID("50000000-0000-4000-8000-000000000021")

ROOT = LineageRun(
    workflow_id=UUID("60000000-0000-4000-8000-000000000001"),
    run_id=UUID("60000000-0000-4000-8000-000000000002"),
)

PARENT = StepLineage(
    step=LineageStep(
        workflow_id=UUID("70000000-0000-4000-8000-000000000001"),
        run_id=UUID("70000000-0000-4000-8000-000000000002"),
        step_id=UUID("70000000-0000-4000-8000-000000000003"),
        attempt=1,
    ),
    depth=2,
    root=ROOT,
)


class RecordingStrategy:
    """Record the lineage active while it runs, failing its first few attempts."""

    def __init__(
        self,
        *,
        failures: int = 0,
        in_thread: bool = False,
    ) -> None:
        self._failures = failures
        self._in_thread = in_thread
        self.seen: list[StepLineage | None] = []

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return StrategyMetadata(
            id=STRATEGY_ID,
            name="Recording step",
            description="Record the active step lineage.",
            version="1.0.0",
        )

    async def run(self, context: Context) -> StrategyOutcome:
        """Record the active lineage, as a tool in this step would see it."""

        if self._in_thread:
            self.seen.append(await asyncio.to_thread(active_step_lineage))
        else:
            self.seen.append(active_step_lineage())

        if self._failures > 0:
            self._failures -= 1
            raise RuntimeError("temporary failure")

        return StrategyOutcome(output="done")


def candidate(
    *steps: WorkflowCandidateStep,
) -> WorkflowCandidate:
    """Return a workflow of the given steps."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Lineage workflow",
            description="Record what each step sees.",
            version="1.0.0",
        ),
        steps=steps,
    )


def step(
    step_id: UUID,
    strategy: RecordingStrategy,
    *,
    depends_on: tuple[UUID, ...] = (),
    attempts: int = 1,
) -> WorkflowCandidateStep:
    """Return one recording step."""

    return WorkflowCandidateStep(
        id=step_id,
        strategy=strategy,
        depends_on=depends_on,
        retry_policy=WorkflowRetryPolicy(max_attempts=attempts),
    )


def child_context() -> Context:
    """Return the initial context of a run started by the parent step."""

    return Context(
        events=(
            ContextEvent(
                event_type="workflow.input.received",
                payload={"input": {}},
                producer="test",
            ),
            create_lineage_event(child_lineage(PARENT, workflow_id=WORKFLOW_ID)),
        )
    )


def test_a_root_runs_steps_see_their_own_run_at_depth_zero() -> None:
    strategy = RecordingStrategy()

    run = asyncio.run(
        WorkflowRunner().run(workflow=candidate(step(FIRST_STEP_ID, strategy)), context=Context())
    )

    own_run = LineageRun(workflow_id=WORKFLOW_ID, run_id=run.id)

    assert strategy.seen == [
        StepLineage(
            step=LineageStep(
                workflow_id=WORKFLOW_ID,
                run_id=run.id,
                step_id=FIRST_STEP_ID,
                attempt=1,
            ),
            depth=0,
            root=own_run,
        )
    ]


def test_a_child_runs_steps_see_its_depth_and_root() -> None:
    strategy = RecordingStrategy()

    run = asyncio.run(
        WorkflowRunner().run(
            workflow=candidate(step(FIRST_STEP_ID, strategy)),
            context=child_context(),
        )
    )

    (seen,) = strategy.seen

    assert seen is not None
    assert seen.depth == 3
    assert seen.root == ROOT
    assert seen.step.run_id == run.id
    assert seen.step.workflow_id == WORKFLOW_ID


def test_the_run_keeps_the_id_its_steps_saw() -> None:
    first = RecordingStrategy()
    later = RecordingStrategy()

    run = asyncio.run(
        WorkflowRunner().run(
            workflow=candidate(
                step(FIRST_STEP_ID, first),
                step(LATER_STEP_ID, later, depends_on=(FIRST_STEP_ID,)),
            ),
            context=Context(),
        )
    )

    run_ids = {seen.step.run_id for seen in (*first.seen, *later.seen) if seen is not None}

    assert run_ids == {run.id}


def test_each_run_gets_its_own_id() -> None:
    strategy = RecordingStrategy()
    workflow = candidate(step(FIRST_STEP_ID, strategy))

    first = asyncio.run(WorkflowRunner().run(workflow=workflow, context=Context()))
    second = asyncio.run(WorkflowRunner().run(workflow=workflow, context=Context()))

    assert first.id != second.id
    assert [seen.step.run_id for seen in strategy.seen if seen is not None] == [
        first.id,
        second.id,
    ]


def test_each_attempt_sees_its_own_attempt_number() -> None:
    strategy = RecordingStrategy(failures=2)

    run = asyncio.run(
        WorkflowRunner().run(
            workflow=candidate(step(FIRST_STEP_ID, strategy, attempts=3)),
            context=Context(),
        )
    )

    assert run.steps[0].status is WorkflowStepStatus.EXECUTED
    assert [seen.step.attempt for seen in strategy.seen if seen is not None] == [1, 2, 3]


def test_concurrent_steps_each_see_their_own_step() -> None:
    first = RecordingStrategy()
    second = RecordingStrategy()

    asyncio.run(
        WorkflowRunner().run(
            workflow=candidate(step(FIRST_STEP_ID, first), step(SECOND_STEP_ID, second)),
            context=Context(),
        )
    )

    assert [seen.step.step_id for seen in first.seen if seen is not None] == [FIRST_STEP_ID]
    assert [seen.step.step_id for seen in second.seen if seen is not None] == [SECOND_STEP_ID]


def test_work_a_step_hands_to_a_thread_sees_its_lineage() -> None:
    strategy = RecordingStrategy(in_thread=True)

    asyncio.run(
        WorkflowRunner().run(
            workflow=candidate(step(FIRST_STEP_ID, strategy)),
            context=child_context(),
        )
    )

    (seen,) = strategy.seen

    assert seen is not None
    assert seen.step.step_id == FIRST_STEP_ID
    assert seen.depth == 3


def test_no_lineage_is_active_outside_a_step() -> None:
    asyncio.run(
        WorkflowRunner().run(
            workflow=candidate(step(FIRST_STEP_ID, RecordingStrategy())),
            context=child_context(),
        )
    )

    assert active_step_lineage() is None


def test_invalid_lineage_in_the_initial_context_stops_the_run_before_any_step() -> None:
    strategy = RecordingStrategy()

    context = Context(
        events=(
            ContextEvent.model_validate(
                {
                    "event_type": "workflow.lineage.received",
                    "payload": {"depth": 1},
                    "producer": "azathoth.lineage",
                }
            ),
        )
    )

    with pytest.raises(LineageError) as error:
        asyncio.run(
            WorkflowRunner().run(
                workflow=candidate(step(FIRST_STEP_ID, strategy)),
                context=context,
            )
        )

    assert str(error.value) == "The context's lineage is not valid lineage: parent: Field required."
    assert strategy.seen == []


def test_a_recorded_failure_keeps_the_run_id_its_steps_saw() -> None:
    strategy = RecordingStrategy(failures=1)

    run = asyncio.run(
        WorkflowRunner().run_recording_failures(
            workflow=candidate(step(FIRST_STEP_ID, strategy)),
            context=Context(),
        )
    )

    assert run.halted
    assert [seen.step.run_id for seen in strategy.seen if seen is not None] == [run.id]
