"""Tests for durable context-aware prompt workflow steps."""

from uuid import UUID

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import ModelRequirements
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    decode_workflow_document,
    encode_workflow_document,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_context_prompt_specification(
    *,
    fixed: bool = False,
) -> ContextPromptStrategySpec:
    """Create one durable context-aware prompt specification."""

    selection = (
        FixedModelSelection(
            provider="openrouter",
            model="example-model",
        )
        if fixed
        else PortfolioModelSelection(
            requirements=ModelRequirements(),
        )
    )

    return ContextPromptStrategySpec(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="Classify request",
            description="Classify externally supplied request text.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text=("Classify this request as positive or negative.\n\nRequest: {request}"),
            bindings=(
                PromptBinding(
                    variable_name="request",
                    event_type="request.received",
                    field_name="input",
                ),
            ),
        ),
        model_selection=selection,
    )


def create_workflow(
    *,
    fixed: bool = False,
) -> WorkflowSpecification:
    """Create one context-aware durable workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Context-aware classification",
            description="Classify one request supplied through execution context.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=create_context_prompt_specification(
                    fixed=fixed,
                ),
            ),
        ),
    )


def test_workflow_step_accepts_context_prompt_specification() -> None:
    specification = create_context_prompt_specification()

    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=specification,
    )

    assert step.specification == specification
    assert isinstance(
        step.specification,
        ContextPromptStrategySpec,
    )


def test_workflow_preserves_context_prompt_specification() -> None:
    workflow = create_workflow()

    specification = workflow.steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )

    assert specification.template.text == (
        "Classify this request as positive or negative.\n\nRequest: {request}"
    )

    assert specification.template.bindings == (
        PromptBinding(
            variable_name="request",
            event_type="request.received",
            field_name="input",
        ),
    )


def test_context_prompt_step_round_trips_through_json() -> None:
    workflow = create_workflow()

    restored = WorkflowSpecification.model_validate_json(
        workflow.model_dump_json(),
    )

    assert restored == workflow

    specification = restored.steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )


def test_workflow_document_preserves_context_prompt_step() -> None:
    workflow = create_workflow()

    restored = decode_workflow_document(
        encode_workflow_document(
            workflow,
        )
    )

    assert restored == workflow

    specification = restored.steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )

    assert specification.template == (create_context_prompt_specification().template)


def test_workflow_document_preserves_context_prompt_portfolio_selection() -> None:
    workflow = create_workflow()

    restored = decode_workflow_document(
        encode_workflow_document(
            workflow,
        )
    )

    specification = restored.steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )

    assert isinstance(
        specification.model_selection,
        PortfolioModelSelection,
    )


def test_workflow_document_preserves_context_prompt_fixed_selection() -> None:
    workflow = create_workflow(
        fixed=True,
    )

    restored = decode_workflow_document(
        encode_workflow_document(
            workflow,
        )
    )

    specification = restored.steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )

    selection = specification.model_selection

    assert isinstance(
        selection,
        FixedModelSelection,
    )

    assert selection.identifier == ("openrouter/example-model")


def test_context_prompt_workflow_can_also_declare_context_backed_inputs() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_context_prompt_specification(),
        inputs=(
            WorkflowInputBinding(
                name="request",
                source=WorkflowContextReference(
                    event_type="request.received",
                    field_name="input",
                ),
            ),
        ),
    )

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Context-aware classification",
            description="Exercise both external-input mechanisms.",
            version="1.0.0",
        ),
        steps=(step,),
    )

    assert workflow.steps[0].inputs == step.inputs
