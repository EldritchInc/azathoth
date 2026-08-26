"""Tests for immutable workflow specification catalogs."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
FIRST_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
FIRST_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
) -> WorkflowSpecification:
    """Create one deterministic workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=strategy_id,
                        name=f"{name} strategy",
                        description=f"Execute the {name} strategy.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text=f"Execute {name}.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_first_workflow() -> WorkflowSpecification:
    """Create the first catalog workflow."""

    return create_workflow(
        workflow_id=FIRST_WORKFLOW_ID,
        step_id=FIRST_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
        name="first workflow",
    )


def create_second_workflow() -> WorkflowSpecification:
    """Create the second catalog workflow."""

    return create_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
        step_id=SECOND_STEP_ID,
        strategy_id=SECOND_STRATEGY_ID,
        name="second workflow",
    )


def test_workflow_catalog_preserves_declaration_order() -> None:
    first = create_first_workflow()
    second = create_second_workflow()

    catalog = WorkflowCatalog(
        specifications=(
            first,
            second,
        ),
    )

    assert catalog.specifications == (
        first,
        second,
    )


def test_workflow_catalog_exposes_identifiers_in_order() -> None:
    catalog = WorkflowCatalog(
        specifications=(
            create_first_workflow(),
            create_second_workflow(),
        ),
    )

    assert catalog.identifiers == (
        FIRST_WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    )


def test_workflow_catalog_gets_specification_by_identifier() -> None:
    first = create_first_workflow()
    second = create_second_workflow()

    catalog = WorkflowCatalog(
        specifications=(
            first,
            second,
        ),
    )

    assert catalog.get(SECOND_WORKFLOW_ID) == second


def test_workflow_catalog_returns_none_for_unknown_identifier() -> None:
    catalog = WorkflowCatalog(
        specifications=(create_first_workflow(),),
    )

    assert catalog.get(SECOND_WORKFLOW_ID) is None


def test_workflow_catalog_finds_specifications_by_name() -> None:
    first = create_first_workflow()

    second = create_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
        step_id=SECOND_STEP_ID,
        strategy_id=SECOND_STRATEGY_ID,
        name="first workflow",
    )

    catalog = WorkflowCatalog(
        specifications=(
            first,
            second,
        ),
    )

    assert catalog.specifications_named("first workflow") == (
        first,
        second,
    )


def test_workflow_catalog_returns_empty_tuple_for_unknown_name() -> None:
    catalog = WorkflowCatalog(
        specifications=(create_first_workflow(),),
    )

    assert catalog.specifications_named("unknown workflow") == ()


def test_workflow_catalog_rejects_duplicate_identifiers() -> None:
    workflow = create_first_workflow()

    with pytest.raises(
        ValidationError,
        match="cannot contain duplicate workflow identifiers",
    ):
        WorkflowCatalog(
            specifications=(
                workflow,
                workflow,
            ),
        )


def test_workflow_catalog_is_immutable() -> None:
    catalog = WorkflowCatalog(
        specifications=(create_first_workflow(),),
    )

    with pytest.raises(ValidationError):
        catalog.specifications = ()
