"""Tests for durable tool-backed workflow step specifications."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
TOOL_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
PROMPT_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_tool_specification() -> ToolStepSpecification:
    """Create a deterministic tool-backed step specification."""

    return ToolStepSpecification(
        requirement=ToolRequirement(
            name="word_count",
            version="1.0.0",
            runtime="python",
        ),
    )


def create_tool_step() -> WorkflowStepSpecification:
    """Create a deterministic tool-backed workflow step."""

    return WorkflowStepSpecification(
        id=TOOL_STEP_ID,
        specification=create_tool_specification(),
        outputs=(
            WorkflowValueBinding(
                name="word_count",
                path=("word_count",),
            ),
        ),
    )


def create_prompt_step() -> WorkflowStepSpecification:
    """Create a deterministic prompt-backed workflow step."""

    return WorkflowStepSpecification(
        id=PROMPT_STEP_ID,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                name="Classify text",
                description="Classify supplied text.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Classify the supplied text.",
            ),
            model_selection=PortfolioModelSelection(
                requirements=ModelRequirements(),
            ),
        ),
        depends_on=(TOOL_STEP_ID,),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a workflow containing tool and prompt steps."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Tool-backed workflow",
            description=("Execute a deterministic tool before a prompt-backed step."),
            version="1.0.0",
        ),
        steps=(
            create_tool_step(),
            create_prompt_step(),
        ),
    )


def test_tool_step_specification_records_requirement() -> None:
    specification = create_tool_specification()

    assert specification.requirement == ToolRequirement(
        name="word_count",
        version="1.0.0",
        runtime="python",
    )


def test_tool_step_specification_is_immutable() -> None:
    specification = create_tool_specification()

    with pytest.raises(ValidationError):
        specification.requirement = ToolRequirement(
            name="character_count",
        )


def test_workflow_step_accepts_tool_specification() -> None:
    step = create_tool_step()

    assert step.id == TOOL_STEP_ID
    assert isinstance(
        step.specification,
        ToolStepSpecification,
    )
    assert step.specification.requirement.name == "word_count"


def test_tool_step_preserves_standard_workflow_outputs() -> None:
    step = create_tool_step()

    assert step.outputs == (
        WorkflowValueBinding(
            name="word_count",
            path=("word_count",),
        ),
    )


def test_workflow_accepts_tool_and_prompt_steps() -> None:
    workflow = create_workflow()

    assert len(workflow.steps) == 2

    assert isinstance(
        workflow.steps[0].specification,
        ToolStepSpecification,
    )
    assert isinstance(
        workflow.steps[1].specification,
        PromptStrategySpec,
    )


def test_tool_step_participates_in_dependency_graph() -> None:
    workflow = create_workflow()

    assert workflow.execution_layers() == (
        (workflow.steps[0],),
        (workflow.steps[1],),
    )


def test_tool_step_specification_round_trips_through_json() -> None:
    specification = create_tool_specification()

    restored = ToolStepSpecification.model_validate_json(
        specification.model_dump_json(),
    )

    assert restored == specification


def test_tool_workflow_step_round_trips_through_json() -> None:
    step = create_tool_step()

    restored = WorkflowStepSpecification.model_validate_json(
        step.model_dump_json(),
    )

    assert restored == step
    assert isinstance(
        restored.specification,
        ToolStepSpecification,
    )


def test_workflow_with_tool_step_round_trips_through_json() -> None:
    workflow = create_workflow()

    restored = WorkflowSpecification.model_validate_json(
        workflow.model_dump_json(),
    )

    assert restored == workflow

    tool_step = restored.steps[0]

    assert isinstance(
        tool_step.specification,
        ToolStepSpecification,
    )
    assert tool_step.specification.requirement == ToolRequirement(
        name="word_count",
        version="1.0.0",
        runtime="python",
    )


def test_tool_step_requires_tool_resolution_configuration() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Tool-backed workflow",
            description="Execute a durable tool.",
            version="1.0.0",
        ),
        steps=(create_tool_step(),),
    )

    with pytest.raises(
        WorkflowGenerationError,
        match="Tool-backed workflow steps require a tool resolver",
    ):
        generate_workflow_candidate(
            specification=workflow,
            catalog=ModelCatalog(),
            registry=LanguageModelRegistry(
                models={},
            ),
        )
