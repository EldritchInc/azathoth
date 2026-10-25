"""Tests that a workflow run which completes has succeeded."""

import asyncio
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.prompting import PromptStrategySpec
from azathoth.providers import Prompt
from azathoth.strategies import Strategy, StrategyMetadata
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocationSuccess,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowNamedValueReference,
    WorkflowProductionEmission,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    complete_production_invocation,
)
from tests.workflows.test_production_execution import (
    INVOCATION_ID,
    PRIMARY,
    WORKFLOW_ID,
    RecordingExecutor,
    create_catalog,
    create_invocation,
    create_registry,
)
from tests.workflows.test_run_observation import (
    FIRST_STEP_ID,
    FIRST_STRATEGY_ID,
    SECOND_STEP_ID,
    SECOND_STRATEGY_ID,
    CountingExecutor,
    create_candidate,
    create_chain,
    create_step,
)

PRIMARY_STEP_ID = UUID("e5000000-0000-4000-8000-000000000011")
FALLBACK_STEP_ID = UUID("e5000000-0000-4000-8000-000000000012")

PRIMARY_STRATEGY_ID = UUID("e5000000-0000-4000-8000-000000000021")
FALLBACK_STRATEGY_ID = UUID("e5000000-0000-4000-8000-000000000022")


class FailingPrimaryExecutor(RecordingExecutor):
    """Fail the `primary` strategy and answer every other strategy.

    Generated prompt strategies append their model to the specified name.
    """

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Fail `primary`, delegating everything else."""

        if strategy.metadata.name.startswith("primary"):
            raise RuntimeError("Primary unavailable.")

        return await super().execute(
            strategy,
            context,
        )


def run_chain(
    *,
    policy: WorkflowFailurePolicy,
) -> WorkflowRun:
    """Run a chain whose first step fails under the given policy."""

    return asyncio.run(
        WorkflowRunner(
            executor=CountingExecutor(
                failing=frozenset({"Counter"}),
            ),
        ).run_recording_failures(
            create_chain(
                first_policy=policy,
            ),
            Context(),
        )
    )


def create_redundant_step(
    *,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
) -> WorkflowStepSpecification:
    """Create one production prompt step answering `answer` and tolerating failure."""

    return WorkflowStepSpecification(
        id=step_id,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=strategy_id,
                name=name,
                description=f"Answer as the {name} producer.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Answer the request.",
            ),
            model_selection=PRIMARY,
        ),
        outputs=(
            WorkflowValueBinding(
                name="answer",
                path=("result",),
            ),
        ),
        failure_policy=WorkflowFailurePolicy.CONTINUE,
    )


def create_redundant_state() -> WorkflowProductionState:
    """Create production state with two redundant producers of `answer`."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="redundant production",
                description="Answer with the first producer that succeeded.",
                version="1.0.0",
            ),
            steps=(
                create_redundant_step(
                    step_id=PRIMARY_STEP_ID,
                    strategy_id=PRIMARY_STRATEGY_ID,
                    name="primary",
                ),
                create_redundant_step(
                    step_id=FALLBACK_STEP_ID,
                    strategy_id=FALLBACK_STRATEGY_ID,
                    name="fallback",
                ),
            ),
            result=WorkflowNamedValueReference(
                name="answer",
            ),
        ),
        emissions=(
            WorkflowProductionEmission(
                name="answer",
                source=WorkflowNamedValueReference(
                    name="answer",
                ),
            ),
        ),
    )


def test_tolerated_continue_failure_completes_and_succeeds() -> None:
    run = run_chain(
        policy=WorkflowFailurePolicy.CONTINUE,
    )

    assert run.failed_step_count == 1
    assert run.succeeded
    assert not run.failed
    assert run.halted is False
    assert run.halting_step_id is None


def test_tolerated_skip_dependents_failure_completes_and_succeeds() -> None:
    run = run_chain(
        policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
    )

    assert run.failed_step_count == 1
    assert run.skipped_step_count == 1
    assert run.succeeded
    assert run.halted is False


def test_fail_workflow_failure_halts_and_fails() -> None:
    run = run_chain(
        policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
    )

    assert run.failed
    assert not run.succeeded
    assert run.halted is True
    assert run.halting_step_id == FIRST_STEP_ID


def test_halting_step_is_the_first_fail_workflow_failure_in_declared_order() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=CountingExecutor(
                failing=frozenset({"Left", "Right"}),
            ),
        ).run_recording_failures(
            create_candidate(
                create_step(
                    step_id=FIRST_STEP_ID,
                    strategy_id=FIRST_STRATEGY_ID,
                    name="Left",
                    failure_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
                ),
                create_step(
                    step_id=SECOND_STEP_ID,
                    strategy_id=SECOND_STRATEGY_ID,
                    name="Right",
                    failure_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
                ),
            ),
            Context(),
        )
    )

    assert run.halting_step_id == FIRST_STEP_ID


def test_run_without_failures_is_not_halted() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=CountingExecutor(),
        ).run_recording_failures(
            create_chain(),
            Context(),
        )
    )

    assert run.succeeded
    assert run.halted is False


def test_halting_round_trips_through_run_json() -> None:
    run = run_chain(
        policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
    )

    restored = WorkflowRun.model_validate_json(run.model_dump_json())

    assert restored == run
    assert restored.halting_step_id == FIRST_STEP_ID


def test_run_recorded_before_halting_with_a_failure_is_still_failed() -> None:
    document = json.loads(
        run_chain(
            policy=WorkflowFailurePolicy.CONTINUE,
        ).model_dump_json()
    )

    del document["halted"]
    del document["halting_step_id"]

    legacy = WorkflowRun.model_validate(document)

    assert legacy.halted is None
    assert legacy.failed


def test_run_recorded_before_halting_without_failures_still_succeeded() -> None:
    document = json.loads(
        asyncio.run(
            WorkflowRunner(
                executor=CountingExecutor(),
            ).run_recording_failures(
                create_chain(),
                Context(),
            )
        ).model_dump_json()
    )

    del document["halted"]
    del document["halting_step_id"]

    assert WorkflowRun.model_validate(document).succeeded


def test_halted_run_must_name_its_halting_step() -> None:
    document = json.loads(
        run_chain(
            policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        ).model_dump_json()
    )

    document["halting_step_id"] = None

    with pytest.raises(
        ValidationError,
        match="A halted workflow run must name the failed step that halted it\\.",
    ):
        WorkflowRun.model_validate(document)


def test_only_a_halted_run_can_name_a_halting_step() -> None:
    document = json.loads(
        run_chain(
            policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        ).model_dump_json()
    )

    document["halted"] = False

    with pytest.raises(
        ValidationError,
        match="Only a halted workflow run can name a halting step\\.",
    ):
        WorkflowRun.model_validate(document)


def test_halting_step_must_be_a_failed_step_of_the_run() -> None:
    document = json.loads(
        run_chain(
            policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        ).model_dump_json()
    )

    document["halting_step_id"] = str(SECOND_STEP_ID)

    with pytest.raises(
        ValidationError,
        match=(f"Workflow run halting step {SECOND_STEP_ID} is not a failed step of the run\\."),
    ):
        WorkflowRun.model_validate(document)


def test_production_invocation_succeeds_when_a_redundant_producer_fails() -> None:
    run_repository = InMemoryWorkflowRunRepository()
    invocation_run_repository = InMemoryProductionInvocationRunRepository()
    invocation_repository = InMemoryProductionInvocationRepository()

    invocation = create_invocation()

    invocation_repository.save(
        invocation,
    )

    result = asyncio.run(
        complete_production_invocation(
            invocation=invocation,
            state=create_redundant_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=FailingPrimaryExecutor(),
            ),
            run_repository=run_repository,
            invocation_repository=invocation_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    assert result == ProductionInvocationSuccess(
        invocation_id=INVOCATION_ID,
        result={
            "answer": "success",
        },
    )

    association = invocation_run_repository.get(INVOCATION_ID)

    assert association is not None

    run = run_repository.get(association.run_id)

    assert run is not None
    assert run.succeeded
    assert run.failed_step_count == 1
