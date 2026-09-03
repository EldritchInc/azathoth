"""Tests for production workflow invocation execution."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import (
    Context,
    ContextEvent,
)
from azathoth.execution import (
    ExecutionResult,
    StrategyExecutor,
)
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    Prompt,
)
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
)
from azathoth.workflows import (
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocation,
    WorkflowMetadata,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    execute_production_invocation,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

REVISION_ID = UUID("44444444-4444-4444-4444-444444444444")

INVOCATION_ID = UUID("55555555-5555-5555-5555-555555555555")

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


class RecordingExecutor(StrategyExecutor):
    """A deterministic executor for production invocation tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[Strategy, Context]] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record execution and return deterministic evidence."""

        self.calls.append(
            (
                strategy,
                context,
            )
        )

        started_at = datetime(
            2026,
            9,
            3,
            12,
            0,
            tzinfo=UTC,
        )

        completed_at = datetime(
            2026,
            9,
            3,
            12,
            0,
            1,
            tzinfo=UTC,
        )

        final_context = context.append(
            ContextEvent(
                event_type="production.test.completed",
                payload={
                    "strategy_name": strategy.metadata.name,
                },
                producer="recording-executor",
            )
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output={
                "result": "success",
            },
            initial_context=context,
            final_context=final_context,
            started_at=started_at,
            completed_at=completed_at,
        )


def create_revision() -> WorkflowProductionRevision:
    """Create deterministic production revision."""

    return WorkflowProductionRevision(
        id=REVISION_ID,
        state=WorkflowProductionState(
            specification=WorkflowSpecification(
                metadata=WorkflowMetadata(
                    id=WORKFLOW_ID,
                    name="production-execution",
                    description="Exercise production execution.",
                    version="1.0.0",
                ),
                steps=(
                    WorkflowStepSpecification(
                        id=STEP_ID,
                        specification=PromptStrategySpec(
                            metadata=StrategyMetadata(
                                id=STRATEGY_ID,
                                name="production-prompt",
                                description="Exercise production execution.",
                                version="1.0.0",
                            ),
                            prompt=Prompt(
                                text="Process the production request.",
                            ),
                            model_selection=PRIMARY,
                        ),
                    ),
                ),
            )
        ),
    )


def create_invocation(
    *,
    revision_id: UUID = REVISION_ID,
    workflow_id: UUID = WORKFLOW_ID,
) -> ProductionInvocation:
    """Create deterministic production invocation."""

    return ProductionInvocation(
        id=INVOCATION_ID,
        workflow_id=workflow_id,
        production_revision_id=revision_id,
        initial_context=Context(),
    )


def create_catalog() -> ModelCatalog:
    """Create current production model catalog."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=PRIMARY.provider,
                model=PRIMARY.model,
                display_name=PRIMARY.identifier,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable production model registry."""

    return LanguageModelRegistry(
        {
            PRIMARY.identifier: DeterministicLanguageModel(
                provider=PRIMARY.provider,
                model=PRIMARY.model,
            ),
        }
    )


def test_execute_production_invocation_returns_workflow_run() -> None:
    revision = create_revision()
    invocation = create_invocation()

    run = asyncio.run(
        execute_production_invocation(
            invocation=invocation,
            revision=revision,
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=RecordingExecutor(),
            ),
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=(InMemoryProductionInvocationRunRepository()),
        )
    )

    assert run.workflow.id == WORKFLOW_ID


def test_execute_production_invocation_uses_invocation_context() -> None:
    revision = create_revision()

    initial_context = Context(
        events=(
            ContextEvent(
                event_type="production.invocation.received",
                payload={
                    "input": {
                        "request": "production payload",
                    },
                },
                producer="azathoth.production",
            ),
        )
    )

    invocation = ProductionInvocation(
        id=INVOCATION_ID,
        workflow_id=WORKFLOW_ID,
        production_revision_id=REVISION_ID,
        initial_context=initial_context,
    )

    executor = RecordingExecutor()

    run = asyncio.run(
        execute_production_invocation(
            invocation=invocation,
            revision=revision,
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=executor,
            ),
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=(InMemoryProductionInvocationRunRepository()),
        )
    )

    assert run.initial_context == invocation.initial_context

    assert executor.calls[0][1] == invocation.initial_context


def test_execute_production_invocation_persists_workflow_run() -> None:
    revision = create_revision()
    invocation = create_invocation()

    run_repository = InMemoryWorkflowRunRepository()

    run = asyncio.run(
        execute_production_invocation(
            invocation=invocation,
            revision=revision,
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=RecordingExecutor(),
            ),
            run_repository=run_repository,
            invocation_run_repository=(InMemoryProductionInvocationRunRepository()),
        )
    )

    assert run_repository.get(run.id) == run


def test_execute_production_invocation_records_run_association() -> None:
    revision = create_revision()
    invocation = create_invocation()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    run = asyncio.run(
        execute_production_invocation(
            invocation=invocation,
            revision=revision,
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(
                executor=RecordingExecutor(),
            ),
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=invocation_run_repository,
        )
    )

    association = invocation_run_repository.get(invocation.id)

    assert association is not None
    assert association.invocation_id == invocation.id
    assert association.run_id == run.id


def test_execute_production_invocation_rejects_wrong_revision() -> None:
    revision = create_revision()

    invocation = create_invocation(
        revision_id=UUID("66666666-6666-6666-6666-666666666666"),
    )

    run_repository = InMemoryWorkflowRunRepository()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    with pytest.raises(
        ValueError,
        match=("Production invocation does not reference the supplied production revision"),
    ):
        asyncio.run(
            execute_production_invocation(
                invocation=invocation,
                revision=revision,
                catalog=create_catalog(),
                registry=create_registry(),
                runner=WorkflowRunner(
                    executor=RecordingExecutor(),
                ),
                run_repository=run_repository,
                invocation_run_repository=invocation_run_repository,
            )
        )

    assert run_repository.runs() == ()
    assert invocation_run_repository.associations() == ()


def test_execute_production_invocation_rejects_wrong_workflow() -> None:
    revision = create_revision()

    invocation = create_invocation(
        workflow_id=UUID("77777777-7777-7777-7777-777777777777"),
    )

    run_repository = InMemoryWorkflowRunRepository()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    with pytest.raises(
        ValueError,
        match=("Production invocation workflow does not match the supplied production revision"),
    ):
        asyncio.run(
            execute_production_invocation(
                invocation=invocation,
                revision=revision,
                catalog=create_catalog(),
                registry=create_registry(),
                runner=WorkflowRunner(
                    executor=RecordingExecutor(),
                ),
                run_repository=run_repository,
                invocation_run_repository=invocation_run_repository,
            )
        )

    assert run_repository.runs() == ()
    assert invocation_run_repository.associations() == ()
