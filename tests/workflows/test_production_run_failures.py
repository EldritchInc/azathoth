"""Tests that production invocations record step failures as durable runs."""

import asyncio

from azathoth.context import Context
from azathoth.execution import (
    ExecutionResult,
    StrategyExecutor,
)
from azathoth.strategies import Strategy
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    WorkflowRunner,
    WorkflowStepStatus,
    complete_production_invocation,
    execute_production_invocation,
)
from tests.workflows.test_production_execution import (
    INVOCATION_ID,
    STEP_ID,
    create_catalog,
    create_invocation,
    create_registry,
    create_state,
)


class FailingExecutor(StrategyExecutor):
    """A strategy executor whose every execution fails."""

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Fail the execution."""

        raise RuntimeError("Production step exploded.")


def test_execute_production_invocation_returns_failed_run_instead_of_raising() -> None:
    run = asyncio.run(
        execute_production_invocation(
            invocation=create_invocation(),
            state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=FailingExecutor(),
            ),
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
        )
    )

    assert run.failed
    assert run.steps[0].step_id == STEP_ID
    assert run.steps[0].status is WorkflowStepStatus.FAILED

    failure = run.steps[0].attempts[-1].failure

    assert failure is not None
    assert failure.message == "Production step exploded."


def test_execute_production_invocation_persists_and_associates_failed_run() -> None:
    run_repository = InMemoryWorkflowRunRepository()
    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    run = asyncio.run(
        execute_production_invocation(
            invocation=create_invocation(),
            state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=FailingExecutor(),
            ),
            run_repository=run_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    association = invocation_run_repository.get(INVOCATION_ID)

    assert run_repository.get(run.id) == run
    assert association is not None
    assert association.run_id == run.id


def test_complete_production_invocation_records_failed_run_evidence() -> None:
    invocation = create_invocation()

    invocation_repository = InMemoryProductionInvocationRepository()
    run_repository = InMemoryWorkflowRunRepository()
    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    invocation_repository.save(
        invocation,
    )

    result = asyncio.run(
        complete_production_invocation(
            invocation=invocation,
            state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=FailingExecutor(),
            ),
            run_repository=run_repository,
            invocation_repository=invocation_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    assert result == ProductionInvocationFailure(
        invocation_id=INVOCATION_ID,
        error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
        message="Production workflow execution failed.",
    )

    association = invocation_run_repository.get(INVOCATION_ID)

    assert association is not None

    run = run_repository.get(association.run_id)

    assert run is not None
    assert run.failed
    assert run.steps[0].status is WorkflowStepStatus.FAILED
