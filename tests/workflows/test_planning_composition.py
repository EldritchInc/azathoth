"""Tests for preserving step configuration during workflow planning."""

from uuid import UUID

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    ModelCapability,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

CLASSIFIER_STEP_ID = UUID("39e169cf-00a6-4728-bc97-ce1d95021470")
QUESTION_STEP_ID = UUID("469d8059-b2cc-4ca8-bc18-b3d377052ff8")
REASONING_STEP_ID = UUID("b4ae6fa8-09df-41a7-94e6-c3eb94ad66a7")

CLASSIFIER_STRATEGY_ID = UUID("20cf4513-4206-413c-a377-d7c6c73d97c2")
QUESTION_STRATEGY_ID = UUID("4e23402c-fbb6-4bd3-9acc-75f75a8062b0")
REASONING_STRATEGY_ID = UUID("efcc83d6-73e6-4d43-b00a-ccf73eac9297")


def create_prompt_step(
    *,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
    requirements: ModelRequirements,
    depends_on: tuple[UUID, ...] = (),
) -> WorkflowStepSpecification:
    """Create a deterministic independently configured prompt step."""

    return WorkflowStepSpecification(
        id=step_id,
        depends_on=depends_on,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=strategy_id,
                name=name,
                description=f"Execute the {name} workflow step.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text=f"Execute {name}.",
            ),
            model_requirements=requirements,
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a workflow with independently configured model-backed steps."""

    classifier = create_prompt_step(
        step_id=CLASSIFIER_STEP_ID,
        strategy_id=CLASSIFIER_STRATEGY_ID,
        name="Math classifier",
        requirements=ModelRequirements(
            required_capabilities=frozenset(
                {
                    ModelCapability.STRUCTURED_OUTPUT,
                }
            ),
            minimum_context_window_tokens=8_000,
        ),
    )

    question_detector = create_prompt_step(
        step_id=QUESTION_STEP_ID,
        strategy_id=QUESTION_STRATEGY_ID,
        name="Question detector",
        requirements=ModelRequirements(
            required_capabilities=frozenset(
                {
                    ModelCapability.STRUCTURED_OUTPUT,
                }
            ),
            minimum_context_window_tokens=16_000,
        ),
    )

    reasoning = create_prompt_step(
        step_id=REASONING_STEP_ID,
        strategy_id=REASONING_STRATEGY_ID,
        name="Tool-capable reasoner",
        requirements=ModelRequirements(
            required_capabilities=frozenset(
                {
                    ModelCapability.TOOL_USE,
                }
            ),
            minimum_context_window_tokens=128_000,
        ),
        depends_on=(
            CLASSIFIER_STEP_ID,
            QUESTION_STEP_ID,
        ),
    )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Classify and resolve request",
            description=("Classify the request before running a tool-capable reasoning step."),
            version="1.0.0",
        ),
        steps=(
            classifier,
            question_detector,
            reasoning,
        ),
    )


def test_execution_layers_preserve_original_step_specifications() -> None:
    workflow = create_workflow()

    layers = workflow.execution_layers()

    assert layers[0][0] is workflow.steps[0]
    assert layers[0][1] is workflow.steps[1]
    assert layers[1][0] is workflow.steps[2]


def test_execution_layers_preserve_step_scoped_model_requirements() -> None:
    workflow = create_workflow()

    layers = workflow.execution_layers()

    classifier_requirements = layers[0][0].specification.model_requirements
    question_requirements = layers[0][1].specification.model_requirements
    reasoning_requirements = layers[1][0].specification.model_requirements

    assert classifier_requirements == ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        minimum_context_window_tokens=8_000,
    )

    assert question_requirements == ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        minimum_context_window_tokens=16_000,
    )

    assert reasoning_requirements == ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        ),
        minimum_context_window_tokens=128_000,
    )


def test_workflow_planning_does_not_create_global_model_requirements() -> None:
    workflow = create_workflow()

    workflow.execution_layers()

    assert "model_requirements" not in WorkflowSpecification.model_fields


def test_steps_in_same_layer_keep_independent_requirements() -> None:
    workflow = create_workflow()

    first_layer = workflow.execution_layers()[0]

    first_requirements = first_layer[0].specification.model_requirements
    second_requirements = first_layer[1].specification.model_requirements

    assert first_requirements != second_requirements
    assert first_requirements.minimum_context_window_tokens == 8_000
    assert second_requirements.minimum_context_window_tokens == 16_000


def test_planned_downstream_step_preserves_dependencies_and_requirements() -> None:
    workflow = create_workflow()

    reasoning_step = workflow.execution_layers()[1][0]

    assert reasoning_step.depends_on == (
        CLASSIFIER_STEP_ID,
        QUESTION_STEP_ID,
    )
    assert (
        ModelCapability.TOOL_USE
        in reasoning_step.specification.model_requirements.required_capabilities
    )
    assert reasoning_step.specification.model_requirements.minimum_context_window_tokens == 128_000


def test_restored_workflow_produces_equivalent_execution_layers() -> None:
    workflow = create_workflow()

    restored = WorkflowSpecification.model_validate_json(workflow.model_dump_json())

    original_layers = tuple(
        tuple(step.id for step in layer) for layer in workflow.execution_layers()
    )
    restored_layers = tuple(
        tuple(step.id for step in layer) for layer in restored.execution_layers()
    )

    assert restored_layers == original_layers

    assert (
        restored.execution_layers()[1][0].specification.model_requirements
        == workflow.execution_layers()[1][0].specification.model_requirements
    )
