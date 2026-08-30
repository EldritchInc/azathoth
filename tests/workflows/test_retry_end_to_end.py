"""End-to-end tests for workflow retry policies."""

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
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("7f7dd7ec-fc88-4a90-9fef-c4df9f4c62f8")
STEP_ID = UUID("6ef4f88e-b53f-495d-b1f5-c4e1d0e0fdb5")
STRATEGY_ID = UUID("cf991d42-d4e6-4c4d-b53b-26eb4aee0b7d")


class StubLanguageModel:
    """A deterministic executable language model."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a deterministic language model response."""

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
    """Fail before eventually succeeding."""

    def __init__(
        self,
        *,
        failures_before_success: int,
    ) -> None:
        self.calls = 0
        self.remaining_failures = failures_before_success

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Execute a strategy."""

        self.calls += 1

        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise RuntimeError("temporary provider failure")

        timestamp = datetime(
            2026,
            8,
            11,
            20,
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
    """Create a retry-enabled workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Retry workflow",
            description="Verify retry policies end to end.",
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


def test_retry_policy_survives_candidate_generation() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].retry_policy == WorkflowRetryPolicy(
        max_attempts=3,
    )


def test_workflow_runner_retries_until_success() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executable_strategy_id = candidate.steps[0].strategy.metadata.id

    executor = FlakyExecutor(
        failures_before_success=2,
    )

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

    assert step.execution is not None

    assert step.execution.output == "success"

    assert step.step_id == STEP_ID

    assert step.execution.strategy_id == executable_strategy_id

    assert step.execution.strategy_id != STRATEGY_ID


def test_retry_policy_exhaustion_propagates_failure() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = FlakyExecutor(
        failures_before_success=3,
    )

    try:
        asyncio.run(
            WorkflowRunner(
                executor=executor,
            ).run(
                workflow=candidate,
                context=Context(),
            )
        )
        raise AssertionError("Workflow execution unexpectedly succeeded.")
    except RuntimeError as error:
        assert "temporary provider failure" in str(error)

    assert executor.calls == 3
