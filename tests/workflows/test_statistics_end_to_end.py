"""End-to-end tests for workflow execution statistics."""

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
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowStepStatus,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("3132c229-91bc-4f24-98af-3fe7a3fd052e")

RETRY_STEP_ID = UUID("f867d49b-8606-4a36-9ff5-f7d2b1fda3c3")
FAILING_STEP_ID = UUID("d9996b19-65f6-4d7f-ab78-89b8d8982bea")
DEPENDENT_STEP_ID = UUID("2181799d-ce2c-47bb-8415-5ce955e12c54")

RETRY_STRATEGY_ID = UUID("395671be-1ffe-4225-9eb7-b506581051b8")
FAILING_STRATEGY_ID = UUID("10b283a7-fe2e-41a2-b235-9f7c1ed56562")
DEPENDENT_STRATEGY_ID = UUID("610ce5ac-e55f-49f8-83ff-71eaee2496d7")


class StubLanguageModel:
    """A deterministic executable language model."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a deterministic model response."""

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


class StatisticsExecutor(StrategyExecutor):
    """Produce retries, permanent failure, and successful execution."""

    def __init__(self) -> None:
        self.retry_calls = 0
        self.failing_calls = 0
        self.dependent_calls = 0

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Execute with deterministic failure behavior."""

        if strategy.metadata.name.startswith("Retry step"):
            self.retry_calls += 1

            if self.retry_calls == 1:
                raise RuntimeError("temporary failure")

        elif strategy.metadata.name.startswith("Failing step"):
            self.failing_calls += 1

            raise RuntimeError("permanent failure")

        elif strategy.metadata.name.startswith("Dependent step"):
            self.dependent_calls += 1

        timestamp = datetime(
            2026,
            8,
            11,
            14,
            0,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=strategy.metadata.name,
            initial_context=context,
            final_context=context,
            started_at=timestamp,
            completed_at=timestamp,
        )


def create_prompt_specification(
    *,
    strategy_id: UUID,
    name: str,
) -> PromptStrategySpec:
    """Create a deterministic prompt strategy specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text=name,
        ),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )


def create_specification() -> WorkflowSpecification:
    """Create a workflow containing retries, failure, and skipped work."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Execution statistics workflow",
            description=(
                "Verify workflow execution statistics from specification through durable execution."
            ),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=RETRY_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=RETRY_STRATEGY_ID,
                    name="Retry step",
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
            ),
            WorkflowStepSpecification(
                id=FAILING_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=FAILING_STRATEGY_ID,
                    name="Failing step",
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            WorkflowStepSpecification(
                id=DEPENDENT_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=DEPENDENT_STRATEGY_ID,
                    name="Dependent step",
                ),
                depends_on=(FAILING_STEP_ID,),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a deterministic model catalog."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="test-model",
                display_name="Test Model",
                context_window_tokens=32_000,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create a deterministic model registry."""

    return LanguageModelRegistry(
        models={
            "test-provider/test-model": StubLanguageModel(),
        }
    )


def test_execution_statistics_are_computed_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = StatisticsExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert executor.retry_calls == 2
    assert executor.failing_calls == 2
    assert executor.dependent_calls == 0

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.SKIPPED,
    )

    statistics = run.statistics

    assert statistics.total_steps == 3
    assert statistics.executed_steps == 1
    assert statistics.failed_steps == 1
    assert statistics.skipped_steps == 1

    assert statistics.total_attempts == 4
    assert statistics.successful_attempts == 1
    assert statistics.failed_attempts == 3

    assert statistics.retry_count == 2

    assert run.executed_step_count == 1
    assert run.failed_step_count == 1
    assert run.skipped_step_count == 1
    assert run.total_attempt_count == 4
    assert run.retry_count == 2

    assert run.failed
    assert not run.succeeded


def test_execution_statistics_match_recorded_history_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=StatisticsExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    statistics = run.statistics

    assert statistics.total_steps == len(run.steps)

    assert statistics.total_attempts == sum(len(step.attempts) for step in run.steps)

    assert statistics.successful_attempts == sum(
        attempt.succeeded for step in run.steps for attempt in step.attempts
    )

    assert statistics.failed_attempts == sum(
        not attempt.succeeded for step in run.steps for attempt in step.attempts
    )

    assert statistics.retry_count == sum(
        max(
            len(step.attempts) - 1,
            0,
        )
        for step in run.steps
    )


def test_execution_statistics_round_trip_with_workflow_run() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=StatisticsExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    restored = WorkflowRun.model_validate_json(run.model_dump_json())

    assert restored == run
    assert restored.statistics == run.statistics

    assert restored.failed
    assert not restored.succeeded

    assert restored.retry_count == 2
    assert restored.total_attempt_count == 4


def test_statistics_do_not_persist_duplicate_derived_state() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=StatisticsExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    serialized = run.model_dump()

    assert "statistics" not in serialized
    assert "succeeded" not in serialized
    assert "failed" not in serialized
    assert "retry_count" not in serialized
