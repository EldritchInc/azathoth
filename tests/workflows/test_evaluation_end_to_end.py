"""End-to-end tests for workflow evaluation."""

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
    WorkflowEvaluation,
    WorkflowFailurePolicy,
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

WORKFLOW_ID = UUID("d5a706a8-34c7-4abf-b70f-2d4503cc1aa7")

RETRY_STEP_ID = UUID("d58f236f-3dd8-4a99-b442-d9ff4c550a60")
FAILING_STEP_ID = UUID("770190bb-a3df-4d5a-a387-d73647d1cbfb")
DEPENDENT_STEP_ID = UUID("1bd4dd68-095b-4ed9-8c20-d65e983739e6")

RETRY_STRATEGY_ID = UUID("43a46d50-cf46-4c5d-9be2-fbd40bf4bc81")
FAILING_STRATEGY_ID = UUID("77551114-dd82-4c69-90f6-d8a421c0fcbb")
DEPENDENT_STRATEGY_ID = UUID("32e53903-4b30-41ae-855b-6168541a3853")


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


class EvaluationExecutor(StrategyExecutor):
    """Produce retry, permanent failure, and skipped dependent work."""

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

        elif strategy.metadata.name.startswith("Failing step"):
            self.failure_calls += 1

            raise RuntimeError("permanent provider failure")

        elif strategy.metadata.name.startswith("Dependent step"):
            self.dependent_calls += 1

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
    """Create a workflow exercising evaluation-relevant behavior."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Workflow evaluation",
            description=(
                "Verify workflow evaluation from specification through durable execution."
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


def test_workflow_evaluation_is_available_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    executor = EvaluationExecutor()

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

    evaluation = run.evaluation

    assert evaluation.workflow_id == WORKFLOW_ID
    assert evaluation.statistics == run.statistics
    assert evaluation.reliability == run.reliability


def test_workflow_evaluation_contains_complete_statistics_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=EvaluationExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    evaluation = run.evaluation

    assert evaluation.statistics.total_steps == 3
    assert evaluation.statistics.executed_steps == 1
    assert evaluation.statistics.failed_steps == 1
    assert evaluation.statistics.skipped_steps == 1

    assert evaluation.statistics.total_attempts == 4
    assert evaluation.statistics.successful_attempts == 1
    assert evaluation.statistics.failed_attempts == 3

    assert evaluation.statistics.retry_count == 2


def test_workflow_evaluation_contains_reliability_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=EvaluationExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    reliability = run.evaluation.reliability

    assert reliability.completion_rate == 1 / 3
    assert reliability.first_attempt_success_rate == 0.0
    assert reliability.retry_rate == 1.0
    assert reliability.failure_rate == 0.5


def test_workflow_evaluation_round_trips_through_json() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=EvaluationExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    evaluation = run.evaluation

    restored = WorkflowEvaluation.model_validate_json(evaluation.model_dump_json())

    assert restored == evaluation

    assert restored.workflow_id == run.workflow.id
    assert restored.statistics == run.statistics
    assert restored.reliability == run.reliability


def test_evaluation_is_derived_not_persisted_in_workflow_run() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=EvaluationExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    serialized_run = run.model_dump()

    assert "evaluation" not in serialized_run
    assert "statistics" not in serialized_run
    assert "reliability" not in serialized_run
