"""Tests for step inputs bound to constant values (ADR 0094)."""

import asyncio
import json
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.context import Context, ContextEvent
from azathoth.prompting import (
    ContextPromptStrategy,
    PromptInputBinding,
    PromptTemplate,
)
from azathoth.providers import (
    ModelResponse,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    PythonToolExecutor,
    ToolImplementation,
    ToolRequirement,
    ToolStrategy,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowConstantValue,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowNamedValueReference,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    decode_workflow_document,
    encode_workflow_document,
)

WORKFLOW_ID = UUID("b0000000-0000-4000-8000-000000000001")

STEP_ID = UUID("b0000000-0000-4000-8000-000000000011")

TOOL_ID = UUID("b0000000-0000-4000-8000-000000000021")

IMPLEMENTATION_ID = UUID("b0000000-0000-4000-8000-000000000031")

PROMPT_STRATEGY_ID = UUID("b0000000-0000-4000-8000-000000000041")

CHILD_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000040"

ECHO_SOURCE = "def run(**inputs):\n    return {'inputs': inputs}\n"


class RecordingModel:
    """Reply `done` and record every prompt."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt and return a fixed reply."""

        self.prompts.append(prompt.text)

        return ModelResponse(
            text="done",
            provider="recording",
            model="model",
            prompt_tokens=len(prompt.text.split()),
            completion_tokens=1,
            total_tokens=len(prompt.text.split()) + 1,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )


def echo_strategy() -> ToolStrategy:
    """Return a tool that returns every input it received."""

    return ToolStrategy(
        metadata=StrategyMetadata(
            id=TOOL_ID,
            name="echo",
            description="Return the inputs.",
            version="1.0.0",
        ),
        implementation=ToolImplementation(
            id=IMPLEMENTATION_ID,
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            version="1.0.0",
            runtime="python",
            source=ECHO_SOURCE,
        ),
        executor=PythonToolExecutor(),
    )


def run_echo(
    *inputs: WorkflowInputBinding,
    context: Context | None = None,
) -> WorkflowRun:
    """Run one echo step with the given input bindings."""

    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="constant inputs",
            description="Bind constants to a step.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=echo_strategy(),
                inputs=inputs,
                outputs=(WorkflowValueBinding(name="inputs", path=("inputs",)),),
            ),
        ),
    )

    return asyncio.run(
        WorkflowRunner().run(
            candidate,
            context if context is not None else Context(),
        )
    )


def echoed(
    run: WorkflowRun,
) -> JsonValue:
    """Return the inputs the echo step received."""

    (value,) = run.values_named("inputs")

    return value.value


def constant(
    name: str,
    value: JsonValue,
) -> WorkflowInputBinding:
    """Bind a constant to one named input."""

    return WorkflowInputBinding(
        name=name,
        source=WorkflowConstantValue(value=value),
    )


def test_constant_value_round_trips_through_json() -> None:
    value = WorkflowConstantValue(value={"workflow_id": CHILD_WORKFLOW_ID, "max_iterations": 3})

    assert WorkflowConstantValue.model_validate_json(value.model_dump_json()) == value


def test_constant_value_serializes_as_only_its_value() -> None:
    assert WorkflowConstantValue(value=[1, 2]).model_dump(mode="json") == {"value": [1, 2]}


def test_constant_value_accepts_null() -> None:
    assert WorkflowConstantValue(value=None).value is None


def test_constant_value_rejects_other_keys() -> None:
    with pytest.raises(ValidationError):
        WorkflowConstantValue.model_validate({"value": 1, "unit": "seconds"})


def test_binding_parses_a_constant_source() -> None:
    binding = WorkflowInputBinding.model_validate(
        {"name": "child_workflow_id", "source": {"value": CHILD_WORKFLOW_ID}},
    )

    assert binding.source == WorkflowConstantValue(value=CHILD_WORKFLOW_ID)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param({"name": "count", "value": 1}, id="named"),
        pytest.param(
            {"producer_step_id": str(STEP_ID), "name": "count", "value": 1},
            id="producer",
        ),
        pytest.param({"event_type": "e", "field_name": "f", "value": 1}, id="context"),
    ],
)
def test_binding_rejects_a_reference_carrying_a_value(
    source: dict[str, JsonValue],
) -> None:
    with pytest.raises(
        ValidationError,
        match="A constant input source holds only 'value'.",
    ):
        WorkflowInputBinding.model_validate({"name": "count", "source": source})


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param({"name": "count"}, WorkflowNamedValueReference, id="named"),
        pytest.param(
            {"producer_step_id": str(STEP_ID), "name": "count"},
            WorkflowValueReference,
            id="producer",
        ),
        pytest.param(
            {"event_type": "e", "field_name": "f"},
            WorkflowContextReference,
            id="context",
        ),
    ],
)
def test_binding_still_parses_every_reference(
    source: dict[str, JsonValue],
    expected: type,
) -> None:
    binding = WorkflowInputBinding.model_validate({"name": "count", "source": source})

    assert isinstance(binding.source, expected)


def test_workflow_with_a_constant_input_needs_no_dependency() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="constant inputs",
            description="Bind a constant to a tool step.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(name="echo", version="1.0.0"),
                ),
                inputs=(constant("child_workflow_id", CHILD_WORKFLOW_ID),),
            ),
        ),
    )

    assert workflow.steps[0].depends_on == ()


def test_workflow_document_round_trips_a_constant_input() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="constant inputs",
            description="Bind a constant to a tool step.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(name="echo", version="1.0.0"),
                ),
                inputs=(constant("settings", {"max_iterations": 3, "state": None}),),
            ),
        ),
    )

    encoded = encode_workflow_document(workflow)

    (step,) = json.loads(encoded)["steps"]

    assert step["inputs"] == [
        {"name": "settings", "source": {"value": {"max_iterations": 3, "state": None}}},
    ]
    assert decode_workflow_document(encoded) == workflow


def test_tool_step_receives_a_constant() -> None:
    run = run_echo(constant("child_workflow_id", CHILD_WORKFLOW_ID))

    assert echoed(run) == {"child_workflow_id": CHILD_WORKFLOW_ID}


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"workflow_id": CHILD_WORKFLOW_ID, "max_iterations": 3}, id="object"),
        pytest.param([1, "two", 3.5], id="list"),
        pytest.param(None, id="null"),
        pytest.param(False, id="boolean"),
    ],
)
def test_constant_values_pass_through_unchanged(
    value: JsonValue,
) -> None:
    assert echoed(run_echo(constant("settings", value))) == {"settings": value}


def test_constant_is_recorded_as_a_bound_input_without_a_producer() -> None:
    run = run_echo(constant("child_workflow_id", CHILD_WORKFLOW_ID))

    execution = run.steps[0].execution

    assert execution is not None

    (bound,) = execution.initial_context.by_type("workflow.input.bound")

    assert bound.producer == "workflow-runner"
    assert bound.payload == {
        "name": "child_workflow_id",
        "value": CHILD_WORKFLOW_ID,
        "constant": True,
    }


def test_constant_and_context_inputs_bind_together() -> None:
    run = run_echo(
        constant("child_workflow_id", CHILD_WORKFLOW_ID),
        WorkflowInputBinding(
            name="request",
            source=WorkflowContextReference(
                event_type="request.received",
                field_name="input",
            ),
        ),
        context=Context(
            events=(
                ContextEvent(
                    event_type="request.received",
                    payload={"input": "write a novel"},
                    producer="request-api",
                ),
            )
        ),
    )

    assert echoed(run) == {
        "child_workflow_id": CHILD_WORKFLOW_ID,
        "request": "write a novel",
    }


def test_prompt_variable_renders_a_constant_input() -> None:
    model = RecordingModel()

    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="constant prompt input",
            description="Render a constant into a prompt.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=ContextPromptStrategy(
                    metadata=StrategyMetadata(
                        id=PROMPT_STRATEGY_ID,
                        name="announce",
                        description="Announce the child workflow.",
                    ),
                    template=PromptTemplate(
                        text="The chapters are written by {child}.",
                        bindings=(
                            PromptInputBinding(
                                variable_name="child",
                                input_name="child_workflow_id",
                            ),
                        ),
                    ),
                    language_model=model,
                ),
                inputs=(constant("child_workflow_id", CHILD_WORKFLOW_ID),),
            ),
        ),
    )

    asyncio.run(WorkflowRunner().run(candidate, Context()))

    assert model.prompts == [f"The chapters are written by {CHILD_WORKFLOW_ID}."]
