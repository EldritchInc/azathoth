"""Tests for durable workflow specification models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("a71a5bfb-e2cc-48d5-a055-985cc6450e48")
STEP_ONE_ID = UUID("7f8cc955-8cbf-407e-a902-7d8c8465696b")
STEP_TWO_ID = UUID("aa2ff5c7-ac35-44e2-af83-caf0b88b95c1")
STEP_THREE_ID = UUID("7f496d81-759b-45a3-91cb-f412abf17613")
UNKNOWN_STEP_ID = UUID("0f14b3fa-f45c-4c49-9c5a-e43ef1c28493")


def create_step(
    *,
    step_id: UUID,
    name: str,
    depends_on: tuple[UUID, ...] = (),
) -> WorkflowStepSpecification:
    """Create a deterministic workflow step specification."""

    return WorkflowStepSpecification(
        id=step_id,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                name=name,
                description=f"Execute the {name.lower()} step.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text=f"Perform the {name.lower()} step.",
            ),
            model_requirements=ModelRequirements(),
        ),
        depends_on=depends_on,
    )


def create_workflow() -> WorkflowSpecification:
    """Create a deterministic workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Support request workflow",
            description=(
                "Classify a request, determine whether tools are needed, and produce a response."
            ),
            version="1.0.0",
        ),
        steps=(
            create_step(
                step_id=STEP_ONE_ID,
                name="Classification",
            ),
            create_step(
                step_id=STEP_TWO_ID,
                name="Response",
            ),
            create_step(
                step_id=STEP_THREE_ID,
                name="Safety check",
            ),
        ),
    )


def test_workflow_specification_records_metadata_and_steps() -> None:
    workflow = create_workflow()

    assert workflow.metadata.id == WORKFLOW_ID
    assert workflow.metadata.name == "Support request workflow"
    assert tuple(step.id for step in workflow.steps) == (
        STEP_ONE_ID,
        STEP_TWO_ID,
        STEP_THREE_ID,
    )


def test_workflow_specification_preserves_step_order() -> None:
    workflow = create_workflow()

    assert tuple(step.specification.metadata.name for step in workflow.steps) == (
        "Classification",
        "Response",
        "Safety check",
    )


def test_workflow_metadata_defaults_version() -> None:
    metadata = WorkflowMetadata(
        name="Simple workflow",
        description="A simple workflow used by a test.",
    )

    assert metadata.version == "1.0.0"


def test_workflow_metadata_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowMetadata(
            name="",
            description="Valid description.",
        )


def test_workflow_metadata_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        WorkflowMetadata(
            name="Valid name",
            description="",
        )


def test_workflow_specification_is_immutable() -> None:
    workflow = create_workflow()

    with pytest.raises(ValidationError):
        workflow.steps = ()


def test_workflow_metadata_is_immutable() -> None:
    metadata = create_workflow().metadata

    with pytest.raises(ValidationError):
        metadata.version = "2.0.0"


def test_workflow_specification_round_trips_through_json() -> None:
    workflow = create_workflow()

    restored = WorkflowSpecification.model_validate_json(workflow.model_dump_json())

    assert restored == workflow


def test_workflow_specification_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                name="Empty workflow",
                description="A workflow without any steps.",
            ),
            steps=(),
        )


def test_workflow_specification_rejects_duplicate_step_ids() -> None:
    duplicate_step = create_step(
        step_id=STEP_ONE_ID,
        name="Classification",
    )

    with pytest.raises(
        ValidationError,
        match="Workflow step identifiers must be unique",
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                name="Invalid workflow",
                description="A workflow containing duplicate step identifiers.",
            ),
            steps=(
                duplicate_step,
                duplicate_step.model_copy(),
            ),
        )


def test_workflow_specification_accepts_distinct_step_ids() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Valid workflow",
            description="A workflow containing distinct step identifiers.",
        ),
        steps=(
            create_step(
                step_id=STEP_ONE_ID,
                name="Classification",
            ),
            create_step(
                step_id=STEP_TWO_ID,
                name="Response",
            ),
        ),
    )

    assert tuple(step.id for step in workflow.steps) == (
        STEP_ONE_ID,
        STEP_TWO_ID,
    )


def test_workflow_rejects_dependency_outside_workflow() -> None:
    """Reject dependencies that do not identify a workflow step."""

    first_step = create_step(
        step_id=STEP_ONE_ID,
        name="First",
    )
    second_step = create_step(
        step_id=STEP_TWO_ID,
        name="Second",
        depends_on=(UNKNOWN_STEP_ID,),
    )

    with pytest.raises(
        ValidationError,
        match=("Workflow step dependencies must reference steps in the same workflow"),
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                name="Invalid dependency workflow",
                description=("A workflow containing an unknown dependency."),
            ),
            steps=(
                first_step,
                second_step,
            ),
        )


def test_workflow_rejects_self_dependency() -> None:
    """Reject a workflow step that depends on itself."""

    step = create_step(
        step_id=STEP_ONE_ID,
        name="Self-dependent",
        depends_on=(STEP_ONE_ID,),
    )

    with pytest.raises(
        ValidationError,
        match="Workflow steps cannot depend on themselves",
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                name="Self-dependent workflow",
                description=("A workflow containing a self-dependent step."),
            ),
            steps=(step,),
        )


def test_workflow_rejects_duplicate_step_dependencies() -> None:
    """Reject repeated dependencies on the same predecessor step."""

    first_step = create_step(
        step_id=STEP_ONE_ID,
        name="First",
    )
    second_step = create_step(
        step_id=STEP_TWO_ID,
        name="Second",
        depends_on=(
            STEP_ONE_ID,
            STEP_ONE_ID,
        ),
    )

    with pytest.raises(
        ValidationError,
        match="Workflow step dependencies must be unique",
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                name="Duplicate dependency workflow",
                description=("A workflow containing a repeated dependency."),
            ),
            steps=(
                first_step,
                second_step,
            ),
        )


def test_workflow_rejects_two_step_dependency_cycle() -> None:
    """Reject a dependency cycle between two workflow steps."""

    first_step = create_step(
        step_id=STEP_ONE_ID,
        name="First",
        depends_on=(STEP_TWO_ID,),
    )
    second_step = create_step(
        step_id=STEP_TWO_ID,
        name="Second",
        depends_on=(STEP_ONE_ID,),
    )

    with pytest.raises(
        ValidationError,
        match="Workflow dependency graph must be acyclic",
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                name="Cyclic workflow",
                description=("A workflow containing a two-step dependency cycle."),
            ),
            steps=(
                first_step,
                second_step,
            ),
        )


def test_workflow_rejects_multi_step_dependency_cycle() -> None:
    """Reject a dependency cycle spanning several workflow steps."""

    first_step = create_step(
        step_id=STEP_ONE_ID,
        name="First",
        depends_on=(STEP_THREE_ID,),
    )
    second_step = create_step(
        step_id=STEP_TWO_ID,
        name="Second",
        depends_on=(STEP_ONE_ID,),
    )
    third_step = create_step(
        step_id=STEP_THREE_ID,
        name="Third",
        depends_on=(STEP_TWO_ID,),
    )

    with pytest.raises(
        ValidationError,
        match="Workflow dependency graph must be acyclic",
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                name="Multi-step cyclic workflow",
                description=("A workflow containing a three-step dependency cycle."),
            ),
            steps=(
                first_step,
                second_step,
                third_step,
            ),
        )


def test_workflow_accepts_linear_dependency_chain() -> None:
    """Accept an acyclic linear sequence of workflow dependencies."""

    first_step = create_step(
        step_id=STEP_ONE_ID,
        name="First",
    )
    second_step = create_step(
        step_id=STEP_TWO_ID,
        name="Second",
        depends_on=(STEP_ONE_ID,),
    )
    third_step = create_step(
        step_id=STEP_THREE_ID,
        name="Third",
        depends_on=(STEP_TWO_ID,),
    )

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Linear workflow",
            description="A valid linear workflow dependency graph.",
        ),
        steps=(
            first_step,
            second_step,
            third_step,
        ),
    )

    assert workflow.steps == (
        first_step,
        second_step,
        third_step,
    )


def test_workflow_accepts_diamond_dependency_graph() -> None:
    """Accept multiple parallel steps that converge downstream."""

    fourth_step_id = UUID("73c23fad-c70b-4f5d-b87d-c469c58163c3")

    root_step = create_step(
        step_id=STEP_ONE_ID,
        name="Root",
    )
    left_step = create_step(
        step_id=STEP_TWO_ID,
        name="Left",
        depends_on=(STEP_ONE_ID,),
    )
    right_step = create_step(
        step_id=STEP_THREE_ID,
        name="Right",
        depends_on=(STEP_ONE_ID,),
    )
    final_step = create_step(
        step_id=fourth_step_id,
        name="Final",
        depends_on=(
            STEP_TWO_ID,
            STEP_THREE_ID,
        ),
    )

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Diamond workflow",
            description="A valid diamond-shaped dependency graph.",
        ),
        steps=(
            root_step,
            left_step,
            right_step,
            final_step,
        ),
    )

    assert workflow.steps[-1].depends_on == (
        STEP_TWO_ID,
        STEP_THREE_ID,
    )


def test_workflow_accepts_multiple_root_steps() -> None:
    """Accept workflows containing several independent root steps."""

    first_root = create_step(
        step_id=STEP_ONE_ID,
        name="First root",
    )
    second_root = create_step(
        step_id=STEP_TWO_ID,
        name="Second root",
    )
    dependent_step = create_step(
        step_id=STEP_THREE_ID,
        name="Dependent",
        depends_on=(
            STEP_ONE_ID,
            STEP_TWO_ID,
        ),
    )

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Multiple root workflow",
            description=("A workflow whose final step depends on two roots."),
        ),
        steps=(
            first_root,
            second_root,
            dependent_step,
        ),
    )

    assert workflow.steps[0].depends_on == ()
    assert workflow.steps[1].depends_on == ()
    assert workflow.steps[2].depends_on == (
        STEP_ONE_ID,
        STEP_TWO_ID,
    )


def test_workflow_dependency_graph_round_trips_through_json() -> None:
    """Preserve workflow dependencies through serialization."""

    first_step = create_step(
        step_id=STEP_ONE_ID,
        name="First",
    )
    second_step = create_step(
        step_id=STEP_TWO_ID,
        name="Second",
        depends_on=(STEP_ONE_ID,),
    )
    third_step = create_step(
        step_id=STEP_THREE_ID,
        name="Third",
        depends_on=(
            STEP_ONE_ID,
            STEP_TWO_ID,
        ),
    )

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Serializable dependency workflow",
            description=("A workflow used to verify graph serialization."),
        ),
        steps=(
            first_step,
            second_step,
            third_step,
        ),
    )

    restored = WorkflowSpecification.model_validate_json(workflow.model_dump_json())

    assert restored == workflow
    assert restored.steps[1].depends_on == (STEP_ONE_ID,)
    assert restored.steps[2].depends_on == (
        STEP_ONE_ID,
        STEP_TWO_ID,
    )
