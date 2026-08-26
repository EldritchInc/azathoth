"""End-to-end tests for workflow reliability metrics."""

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
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("45c1ef79-545d-4fa6-80e1-0f6b93cc16bb")

RETRY_STEP_ID = UUID("bb8351c5-f20d-4c64-99ac-9cc68da661a7")
FAILURE_STEP_ID = UUID("52f50813-f7f4-4b93-bdd9-5917fd131d06")
DEPENDENT_STEP_ID = UUID("3a59cf70-c0d9-4bf0-a760-4b33d48ddf40")

RETRY_STRATEGY_ID = UUID("171290a1-f574-4d67-87b5-2f78b6aeb623")
FAILURE_STRATEGY_ID = UUID("7951ae23-9852-4df3-88e0-3c58bd20fa43")
DEPENDENT_STRATEGY_ID = UUID("4d8d6ea3-4fad-4911-9c43-17195ba76668")


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


class ReliabilityExecutor(StrategyExecutor):
    """Produce one recovered retry and one permanent failure."""

    def __init__(self) -> None:
        self.retry_calls = 0
        self.failure_calls = 0
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
                raise RuntimeError("temporary provider failure")

        elif strategy.metadata.name.startswith("Failure step"):
            self.failure_calls += 1

            raise RuntimeError("permanent provider failure")

        elif strategy.metadata.name.startswith("Dependent step"):
            self.dependent_calls += 1

        timestamp = datetime(
            2026,
            8,
            11,
            15,
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
    """Create a workflow with retry, failure, and skipped work."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Reliability workflow",
            description=("Verify workflow reliability metrics end to end."),
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
                id=FAILURE_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=FAILURE_STRATEGY_ID,
                    name="Failure step",
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
                depends_on=(FAILURE_STEP_ID,),
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


def test_reliability_metrics_are_computed_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = ReliabilityExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert executor.retry_calls == 2
    assert executor.failure_calls == 2
    assert executor.dependent_calls == 0

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.SKIPPED,
    )

    reliability = run.reliability

    assert reliability.completion_rate == 1 / 3

    assert reliability.first_attempt_success_rate == 0.0
    assert reliability.retry_rate == 1.0
    assert reliability.failure_rate == 0.5


def test_reliability_metrics_match_recorded_history_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ReliabilityExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    attempted_steps = tuple(step for step in run.steps if step.attempts)

    assert len(attempted_steps) == 2

    first_attempt_successes = sum(step.attempts[0].succeeded for step in attempted_steps)

    retried_steps = sum(len(step.attempts) > 1 for step in attempted_steps)

    failed_steps = sum(step.status is WorkflowStepStatus.FAILED for step in attempted_steps)

    reliability = run.reliability

    assert reliability.first_attempt_success_rate == (
        first_attempt_successes / len(attempted_steps)
    )

    assert reliability.retry_rate == (retried_steps / len(attempted_steps))

    assert reliability.failure_rate == (failed_steps / len(attempted_steps))


def test_reliability_metrics_survive_workflow_run_round_trip() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ReliabilityExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    restored = WorkflowRun.model_validate_json(run.model_dump_json())

    assert restored == run
    assert restored.reliability == run.reliability

    assert restored.reliability.completion_rate == 1 / 3
    assert restored.reliability.retry_rate == 1.0
    assert restored.reliability.failure_rate == 0.5


def test_reliability_metrics_are_derived_not_persisted() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ReliabilityExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    serialized = run.model_dump()

    assert "reliability" not in serialized
