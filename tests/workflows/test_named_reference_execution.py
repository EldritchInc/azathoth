"""Tests for resolving name-only workflow inputs during execution."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowNamedValueReference,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
)

WORKFLOW_ID = UUID("d4b2e7f3-5c6a-4f81-8b92-3c4d5e6f7a01")

PRIMARY_STEP_ID = UUID("d4b2e7f3-5c6a-4f81-8b92-3c4d5e6f7a11")
FALLBACK_STEP_ID = UUID("d4b2e7f3-5c6a-4f81-8b92-3c4d5e6f7a12")
CONSUMER_STEP_ID = UUID("d4b2e7f3-5c6a-4f81-8b92-3c4d5e6f7a13")

PRIMARY_STRATEGY_ID = UUID("d4b2e7f3-5c6a-4f81-8b92-3c4d5e6f7a21")
FALLBACK_STRATEGY_ID = UUID("d4b2e7f3-5c6a-4f81-8b92-3c4d5e6f7a22")
CONSUMER_STRATEGY_ID = UUID("d4b2e7f3-5c6a-4f81-8b92-3c4d5e6f7a23")

NO_FAILURES: frozenset[str] = frozenset()

EXECUTION_TIME = datetime(
    2026,
    10,
    23,
    13,
    0,
    tzinfo=UTC,
)

ADDRESS_OUTPUT = (
    WorkflowValueBinding(
        name="address",
        path=("address",),
    ),
)


class NamedStrategy:
    """A strategy identified only by its name."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return a placeholder outcome."""

        return StrategyOutcome(
            output=self.metadata.name,
        )


class AddressExecutor(StrategyExecutor):
    """Answer with an address named after the strategy, or fail."""

    def __init__(
        self,
        *,
        failing: frozenset[str] = NO_FAILURES,
    ) -> None:
        self._failing = failing
        self.bound_inputs: dict[str, list[dict[str, JsonValue]]] = {}

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record bound inputs, then answer or fail."""

        name = strategy.metadata.name

        self.bound_inputs[name] = [
            dict(event.payload)
            for event in context.events
            if event.event_type == "workflow.input.bound"
        ]

        if name in self._failing:
            raise RuntimeError(f"{name} failed")

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=name,
            strategy_version=strategy.metadata.version,
            output={
                "address": f"{name.lower()} address",
            },
            initial_context=context,
            final_context=context,
            started_at=EXECUTION_TIME,
            completed_at=EXECUTION_TIME,
        )


def create_candidate(
    *,
    consumer_depends_on: tuple[UUID, ...] = (
        PRIMARY_STEP_ID,
        FALLBACK_STEP_ID,
    ),
) -> WorkflowCandidate:
    """Create a workflow whose consumer names a redundantly produced address."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Redundant address lookup",
            description="Look an address up two ways and use whichever answered.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=PRIMARY_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=PRIMARY_STRATEGY_ID,
                    name="Primary",
                ),
                outputs=ADDRESS_OUTPUT,
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            WorkflowCandidateStep(
                id=FALLBACK_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=FALLBACK_STRATEGY_ID,
                    name="Fallback",
                ),
                outputs=ADDRESS_OUTPUT,
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            WorkflowCandidateStep(
                id=CONSUMER_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=CONSUMER_STRATEGY_ID,
                    name="Consumer",
                ),
                depends_on=consumer_depends_on,
                inputs=(
                    WorkflowInputBinding(
                        name="location",
                        source=WorkflowNamedValueReference(
                            name="address",
                        ),
                    ),
                ),
            ),
        ),
    )


def run_candidate(
    executor: AddressExecutor,
    candidate: WorkflowCandidate,
) -> None:
    """Run one candidate to completion."""

    asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )


def test_name_only_input_uses_the_first_declared_producer() -> None:
    executor = AddressExecutor()

    run_candidate(
        executor,
        create_candidate(),
    )

    assert executor.bound_inputs["Consumer"] == [
        {
            "name": "location",
            "value": "primary address",
            "producer_step_id": str(PRIMARY_STEP_ID),
            "source_name": "address",
        }
    ]


def test_name_only_input_prefers_workflow_step_order_over_dependency_order() -> None:
    executor = AddressExecutor()

    run_candidate(
        executor,
        create_candidate(
            consumer_depends_on=(
                FALLBACK_STEP_ID,
                PRIMARY_STEP_ID,
            ),
        ),
    )

    assert executor.bound_inputs["Consumer"][0]["producer_step_id"] == str(PRIMARY_STEP_ID)


def test_name_only_input_passes_over_a_failed_producer() -> None:
    executor = AddressExecutor(
        failing=frozenset({"Primary"}),
    )

    run_candidate(
        executor,
        create_candidate(),
    )

    assert executor.bound_inputs["Consumer"] == [
        {
            "name": "location",
            "value": "fallback address",
            "producer_step_id": str(FALLBACK_STEP_ID),
            "source_name": "address",
        }
    ]


def test_name_only_input_ignores_producers_outside_dependencies() -> None:
    executor = AddressExecutor()

    run_candidate(
        executor,
        create_candidate(
            consumer_depends_on=(FALLBACK_STEP_ID,),
        ),
    )

    assert executor.bound_inputs["Consumer"][0]["value"] == "fallback address"


def test_name_only_input_records_the_consumer_as_executed() -> None:
    executor = AddressExecutor(
        failing=frozenset({"Primary"}),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.EXECUTED,
    )


def test_name_only_input_without_any_surviving_producer_still_raises() -> None:
    with pytest.raises(
        RuntimeError,
        match="Validated workflow input could not resolve a committed workflow value.",
    ):
        run_candidate(
            AddressExecutor(
                failing=frozenset(
                    {
                        "Primary",
                        "Fallback",
                    }
                ),
            ),
            create_candidate(),
        )
