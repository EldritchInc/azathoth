"""End-to-end tests for workflow failure policies."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.prompting import PromptStrategySpec
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

WORKFLOW_ID = UUID("f0a54ca1-1f73-47de-9f88-9ce535012d58")

FAILING_STEP_ID = UUID("df9a10a2-fb35-49b4-9663-9d4f47ccb391")
INDEPENDENT_STEP_ID = UUID("becc86f0-9832-4669-82e2-c868cce52e18")
DEPENDENT_STEP_ID = UUID("f3617140-05e0-461c-b7e0-c1a3ab17f156")

FAILING_STRATEGY_ID = UUID("2728fb14-85d9-4362-a730-8c0ea54d28e0")
INDEPENDENT_STRATEGY_ID = UUID("14e2288b-86db-49e1-b1e6-001a4e71e9ce")
DEPENDENT_STRATEGY_ID = UUID("87b53a51-a007-44c5-82a8-f6197db4a411")


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


class FailurePolicyExecutor(StrategyExecutor):
    """Fail one generated strategy and execute the others."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Execute or fail the supplied strategy."""

        self.calls.append(strategy.metadata.name)

        if strategy.metadata.name.startswith("Failing step"):
            raise RuntimeError("provider unavailable")

        timestamp = datetime(
            2026,
            8,
            11,
            13,
            30,
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
        model_requirements=ModelRequirements(),
    )


def create_specification(
    *,
    failure_policy: WorkflowFailurePolicy,
) -> WorkflowSpecification:
    """Create a workflow containing failed and surviving branches."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Failure policy workflow",
            description=(
                "Verify workflow failure policies from specification through durable execution."
            ),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=FAILING_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=FAILING_STRATEGY_ID,
                    name="Failing step",
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
                failure_policy=failure_policy,
            ),
            WorkflowStepSpecification(
                id=INDEPENDENT_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=INDEPENDENT_STRATEGY_ID,
                    name="Independent step",
                ),
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


def test_continue_policy_survives_generation_and_execution() -> None:
    specification = create_specification(
        failure_policy=WorkflowFailurePolicy.CONTINUE,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].failure_policy is WorkflowFailurePolicy.CONTINUE

    executor = FailurePolicyExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    failed = run.steps[0]
    independent = run.steps[1]
    dependent = run.steps[2]

    assert failed.status is WorkflowStepStatus.FAILED
    assert failed.execution is None

    assert tuple(attempt.attempt_number for attempt in failed.attempts) == (
        1,
        2,
    )

    assert all(not attempt.succeeded for attempt in failed.attempts)

    assert independent.status is WorkflowStepStatus.EXECUTED
    assert dependent.status is WorkflowStepStatus.EXECUTED

    assert executor.calls == [
        "Failing step [test-provider/test-model]",
        "Failing step [test-provider/test-model]",
        "Independent step [test-provider/test-model]",
        "Dependent step [test-provider/test-model]",
    ]


def test_skip_dependents_policy_survives_generation_and_execution() -> None:
    specification = create_specification(
        failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].failure_policy is WorkflowFailurePolicy.SKIP_DEPENDENTS

    executor = FailurePolicyExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    failed = run.steps[0]
    independent = run.steps[1]
    dependent = run.steps[2]

    assert failed.status is WorkflowStepStatus.FAILED
    assert independent.status is WorkflowStepStatus.EXECUTED
    assert dependent.status is WorkflowStepStatus.SKIPPED

    assert dependent.execution is None
    assert dependent.attempts == ()
    assert dependent.values == ()

    assert executor.calls == [
        "Failing step [test-provider/test-model]",
        "Failing step [test-provider/test-model]",
        "Independent step [test-provider/test-model]",
    ]


def test_failed_workflow_run_round_trips_through_json() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(
            failure_policy=WorkflowFailurePolicy.CONTINUE,
        ),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=FailurePolicyExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    restored = WorkflowRun.model_validate_json(run.model_dump_json())

    assert restored == run

    failed = restored.steps[0]

    assert failed.status is WorkflowStepStatus.FAILED
    assert failed.execution is None
    assert len(failed.attempts) == 2

    first_failure = failed.attempts[0].failure
    second_failure = failed.attempts[1].failure

    assert first_failure is not None
    assert second_failure is not None

    assert first_failure.exception_type == "RuntimeError"
    assert first_failure.message == "provider unavailable"

    assert second_failure.exception_type == "RuntimeError"
    assert second_failure.message == "provider unavailable"


def test_failure_policy_workflow_preserves_declared_step_order() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(
            failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
        ),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=FailurePolicyExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.step_id for step in run.steps) == (
        FAILING_STEP_ID,
        INDEPENDENT_STEP_ID,
        DEPENDENT_STEP_ID,
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.SKIPPED,
    )
