"""End-to-end tests for workflow execution attempt history."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
)
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("edbe6140-8a93-4d77-a9fd-b1fb72dc9d1d")
STEP_ID = UUID("96ff2f58-f5fd-4ef5-b27d-c95a6df11b4f")
STRATEGY_ID = UUID("18d9ef3d-41d6-44e6-9f75-d14d68bc15d7")


class StubLanguageModel:
    """A deterministic executable language model."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        return ModelResponse(
            text="unused",
            provider="test-provider",
            model="test-model",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=1,
            estimated_cost_usd=0.0,
        )


class FlakyExecutor(StrategyExecutor):
    """Fail twice before succeeding."""

    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        self.calls += 1

        if self.calls < 3:
            raise RuntimeError("temporary provider failure")

        timestamp = datetime(
            2026,
            8,
            11,
            21,
            0,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output="success",
            initial_context=context,
            final_context=context,
            started_at=timestamp,
            completed_at=timestamp,
        )


def create_specification() -> WorkflowSpecification:
    """Create a retry-enabled workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Attempt history workflow",
            description="Verify durable retry history.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Retry step",
                        description="Retry step.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Retry.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a deterministic catalog."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="test-model",
                display_name="Test Model",
                context_window_tokens=32000,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create a deterministic registry."""

    return LanguageModelRegistry(
        models={
            "test-provider/test-model": StubLanguageModel(),
        }
    )


def test_workflow_run_records_complete_attempt_history() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = FlakyExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert executor.calls == 3

    assert len(run.steps) == 1

    step = run.steps[0]

    assert step.status is WorkflowStepStatus.EXECUTED

    assert len(step.attempts) == 3

    assert tuple(attempt.attempt_number for attempt in step.attempts) == (
        1,
        2,
        3,
    )

    assert tuple(attempt.succeeded for attempt in step.attempts) == (
        False,
        False,
        True,
    )

    first_failure = step.attempts[0].failure
    second_failure = step.attempts[1].failure

    assert first_failure is not None
    assert second_failure is not None

    assert first_failure.exception_type == "RuntimeError"
    assert second_failure.exception_type == "RuntimeError"

    assert step.attempts[2].execution == step.execution

    assert step.execution is not None
    assert step.execution.output == "success"

    generated_strategy_id = candidate.steps[0].strategy.metadata.id

    assert step.execution.strategy_id == generated_strategy_id

    assert step.step_id == STEP_ID


def test_attempt_history_round_trips_through_workflow_run() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=FlakyExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    restored = type(run).model_validate_json(run.model_dump_json())

    assert restored == run

    attempts = restored.steps[0].attempts

    assert len(attempts) == 3

    assert attempts[-1].succeeded
