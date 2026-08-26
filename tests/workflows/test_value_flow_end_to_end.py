"""End-to-end tests for workflow value propagation."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

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
from azathoth.strategies import Strategy, StrategyMetadata
from azathoth.workflows import (
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("14a7907d-e7bd-4aec-81a7-57d34f31089c")

CLASSIFIER_STEP_ID = UUID("e3f36e9d-2db2-4421-bddc-448572e03ced")
REASONER_STEP_ID = UUID("262569bd-f7cf-4734-a027-d9272c502619")

CLASSIFIER_STRATEGY_ID = UUID("dc84b3cc-6da9-426f-a4bb-9586ed1133f1")
REASONER_STRATEGY_ID = UUID("85c23619-0912-49ec-85d6-8a1ad487de06")


class StubLanguageModel:
    """A deterministic executable language model."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
    ) -> None:
        self._provider = provider
        self._model = model

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a deterministic model response."""

        return ModelResponse(
            text="unused",
            provider=self._provider,
            model=self._model,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=1,
            estimated_cost_usd=0.0,
        )


class ValueFlowExecutor(StrategyExecutor):
    """Execute workflow strategies with deterministic structured outputs."""

    def __init__(self) -> None:
        self.calls: list[tuple[Strategy, Context]] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Return structured outputs and record received workflow inputs."""

        self.calls.append((strategy, context))

        started_at = datetime(
            2026,
            8,
            9,
            16,
            0,
            tzinfo=UTC,
        )
        completed_at = datetime(
            2026,
            8,
            9,
            16,
            0,
            1,
            tzinfo=UTC,
        )

        output: JsonValue

        if strategy.metadata.name.startswith("Classify"):
            output = {
                "classification": "math",
                "confidence": 0.99,
            }
        else:
            received_inputs: dict[str, JsonValue] = {
                str(event.payload["name"]): event.payload["value"]
                for event in context.events
                if event.event_type == "workflow.input.bound"
            }

            output = {
                "received_inputs": received_inputs,
            }

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=output,
            initial_context=context,
            final_context=context,
            started_at=started_at,
            completed_at=completed_at,
        )


def create_workflow_specification() -> WorkflowSpecification:
    """Create a workflow that exports and consumes a workflow value."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Workflow value flow",
            description=("Classify a request and pass the result to a downstream step."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=CLASSIFIER_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=CLASSIFIER_STRATEGY_ID,
                        name="Classify request",
                        description="Classify the request.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify the request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=REASONER_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=REASONER_STRATEGY_ID,
                        name="Reason about request",
                        description=("Reason using the upstream classification."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Reason about the classified request.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                depends_on=(CLASSIFIER_STEP_ID,),
                inputs=(
                    WorkflowInputBinding(
                        name="route",
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFIER_STEP_ID,
                            name="classification",
                        ),
                    ),
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a catalog containing one eligible model."""

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
    """Create the executable model registry."""

    return LanguageModelRegistry(
        models={
            "test-provider/test-model": StubLanguageModel(
                provider="test-provider",
                model="test-model",
            ),
        }
    )


def test_workflow_values_flow_end_to_end() -> None:
    specification = create_workflow_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert candidate.steps[0].outputs == (
        WorkflowValueBinding(
            name="classification",
            path=("classification",),
        ),
    )
    assert candidate.steps[1].inputs == (
        WorkflowInputBinding(
            name="route",
            source=WorkflowValueReference(
                producer_step_id=CLASSIFIER_STEP_ID,
                name="classification",
            ),
        ),
    )

    executor = ValueFlowExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    classification_values = run.values_named("classification")

    assert len(classification_values) == 1
    assert classification_values[0].value == "math"
    assert classification_values[0].producer_step_id == CLASSIFIER_STEP_ID

    reasoner_context = executor.calls[1][1]

    input_events = tuple(
        event for event in reasoner_context.events if event.event_type == "workflow.input.bound"
    )

    assert len(input_events) == 1
    assert input_events[0].payload["name"] == "route"
    assert input_events[0].payload["value"] == "math"
    assert input_events[0].payload["source_name"] == "classification"
    assert input_events[0].payload["producer_step_id"] == str(CLASSIFIER_STEP_ID)

    assert all(event.event_type != "workflow.input.bound" for event in run.final_context.events)

    assert tuple(step.step_id for step in run.steps) == (
        CLASSIFIER_STEP_ID,
        REASONER_STEP_ID,
    )
