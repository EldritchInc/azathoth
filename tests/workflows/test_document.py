"""Tests for workflow JSON document serialization."""

import json
from uuid import UUID

import pytest

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelCapability,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowDocumentError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    decode_workflow_document,
    encode_workflow_document,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

PROMPT_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

PROMPT_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

TOOL_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_workflow() -> WorkflowSpecification:
    """Create one workflow covering prompt and tool specifications."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="JSON document workflow",
            description=("Exercise durable workflow JSON serialization."),
            version="1.2.3",
        ),
        steps=(
            WorkflowStepSpecification(
                id=PROMPT_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=PROMPT_STRATEGY_ID,
                        name="classify",
                        description=("Classify one request."),
                        version="2.0.0",
                    ),
                    prompt=Prompt(
                        text=("Classify the request and return the expected result."),
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(
                            required_capabilities=frozenset(
                                {
                                    ModelCapability.STRUCTURED_OUTPUT,
                                }
                            ),
                        )
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="normalize result",
                        version="1.0.0",
                        runtime="python",
                    )
                ),
                depends_on=(PROMPT_STEP_ID,),
            ),
        ),
    )


def require_portfolio_requirements(
    specification: PromptStrategySpec,
) -> ModelRequirements:
    """Return requirements from a portfolio-selected prompt specification."""

    selection = specification.model_selection

    assert isinstance(
        selection,
        PortfolioModelSelection,
    )

    return selection.requirements


def test_workflow_document_round_trips_complete_specification() -> None:
    original = create_workflow()

    document = encode_workflow_document(original)

    restored = decode_workflow_document(document)

    assert restored == original
    assert restored is not original


def test_workflow_document_is_valid_json() -> None:
    document = encode_workflow_document(create_workflow())

    payload = json.loads(document)

    assert isinstance(
        payload,
        dict,
    )

    assert payload["metadata"]["id"] == str(WORKFLOW_ID)

    assert payload["metadata"]["name"] == ("JSON document workflow")

    assert len(payload["steps"]) == 2


def test_workflow_document_is_human_readable() -> None:
    document = encode_workflow_document(create_workflow())

    assert document.startswith("{\n")

    assert '\n  "metadata": {' in document

    assert '\n  "steps": [' in document


def test_workflow_document_preserves_prompt_specification() -> None:
    restored = decode_workflow_document(encode_workflow_document(create_workflow()))

    prompt_step = restored.steps[0]

    assert isinstance(
        prompt_step.specification,
        PromptStrategySpec,
    )

    assert prompt_step.specification.metadata.id == PROMPT_STRATEGY_ID

    assert prompt_step.specification.metadata.name == "classify"

    assert prompt_step.specification.prompt.text == (
        "Classify the request and return the expected result."
    )

    assert require_portfolio_requirements(
        prompt_step.specification
    ).required_capabilities == frozenset(
        {
            ModelCapability.STRUCTURED_OUTPUT,
        }
    )


def test_workflow_document_preserves_tool_specification() -> None:
    restored = decode_workflow_document(encode_workflow_document(create_workflow()))

    tool_step = restored.steps[1]

    assert isinstance(
        tool_step.specification,
        ToolStepSpecification,
    )

    assert tool_step.specification.requirement.name == "normalize result"

    assert tool_step.specification.requirement.version == "1.0.0"

    assert tool_step.specification.requirement.runtime == "python"

    assert tool_step.depends_on == (PROMPT_STEP_ID,)


def test_workflow_document_preserves_default_workflow_behavior() -> None:
    original = create_workflow()

    restored = decode_workflow_document(encode_workflow_document(original))

    for original_step, restored_step in zip(
        original.steps,
        restored.steps,
        strict=True,
    ):
        assert restored_step.inputs == original_step.inputs

        assert restored_step.outputs == original_step.outputs

        assert restored_step.conditions == original_step.conditions

        assert restored_step.retry_policy == original_step.retry_policy

        assert restored_step.failure_policy == original_step.failure_policy


def test_workflow_document_rejects_malformed_json() -> None:
    with pytest.raises(
        WorkflowDocumentError,
        match=("Workflow document is not a valid WorkflowSpecification"),
    ):
        decode_workflow_document("{this is definitely not json")


def test_workflow_document_rejects_wrong_document_shape() -> None:
    with pytest.raises(
        WorkflowDocumentError,
        match=("Workflow document is not a valid WorkflowSpecification"),
    ):
        decode_workflow_document('{"hello":"eldritch"}')


def test_workflow_document_rejects_invalid_workflow_domain_data() -> None:
    document = """
{
  "metadata": {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "",
    "description": "Invalid because the name is empty.",
    "version": "1.0.0"
  },
  "steps": []
}
""".strip()

    with pytest.raises(
        WorkflowDocumentError,
        match=("Workflow document is not a valid WorkflowSpecification"),
    ):
        decode_workflow_document(document)


def test_workflow_document_error_preserves_validation_cause() -> None:
    try:
        decode_workflow_document('{"invalid":true}')
    except WorkflowDocumentError as exc:
        assert exc.__cause__ is not None
    else:
        raise AssertionError("Expected invalid workflow document to fail.")
