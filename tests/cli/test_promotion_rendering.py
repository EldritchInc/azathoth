"""Tests for rendering workflow production promotions."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import render_workflow_promotion
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

REVISION_ID = UUID("44444444-4444-4444-4444-444444444444")

CREATED_AT = datetime(
    2026,
    9,
    4,
    22,
    0,
    tzinfo=UTC,
)

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="primary",
)

FIRST_SUBSTITUTE = FixedModelSelection(
    provider="test-provider",
    model="first-substitute",
)

SECOND_SUBSTITUTE = FixedModelSelection(
    provider="other-provider",
    model="second-substitute",
)


def create_revision(
    *,
    model_substitutions: tuple[WorkflowProductionModelSubstitution, ...] = (),
) -> WorkflowProductionRevision:
    """Create one deterministic production promotion revision."""

    return WorkflowProductionRevision(
        id=REVISION_ID,
        state=WorkflowProductionState(
            specification=WorkflowSpecification(
                metadata=WorkflowMetadata(
                    id=WORKFLOW_ID,
                    name="production-promotion",
                    description="Exercise promotion rendering.",
                    version="1.0.0",
                ),
                steps=(
                    WorkflowStepSpecification(
                        id=STEP_ID,
                        specification=PromptStrategySpec(
                            metadata=StrategyMetadata(
                                id=STRATEGY_ID,
                                name="production-prompt",
                                description="Exercise promotion rendering.",
                                version="1.0.0",
                            ),
                            prompt=Prompt(
                                text="Return success.",
                            ),
                            model_selection=PRIMARY,
                        ),
                    ),
                ),
            ),
            model_substitutions=model_substitutions,
        ),
        created_at=CREATED_AT,
    )


def test_render_workflow_promotion_identifies_deployment() -> None:
    rendered = render_workflow_promotion(
        create_revision(),
    )

    assert rendered == "\n".join(
        (
            "Workflow: production-promotion",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Revision ID: {REVISION_ID}",
            "Status: promoted",
            f"Created At: {CREATED_AT.isoformat()}",
            "",
            f"Prompt Step: {STEP_ID}",
            f"Primary Model: {PRIMARY.identifier}",
        )
    )


def test_render_workflow_promotion_includes_ordered_model_substitutes() -> None:
    rendered = render_workflow_promotion(
        create_revision(
            model_substitutions=(
                WorkflowProductionModelSubstitution(
                    step_id=STEP_ID,
                    substitutes=(
                        FIRST_SUBSTITUTE,
                        SECOND_SUBSTITUTE,
                    ),
                ),
            )
        )
    )

    assert (
        "Substitute Models: "
        f"{FIRST_SUBSTITUTE.identifier}, {SECOND_SUBSTITUTE.identifier}" in rendered
    )

    assert rendered.index(
        FIRST_SUBSTITUTE.identifier,
    ) < rendered.index(
        SECOND_SUBSTITUTE.identifier,
    )


def test_render_workflow_promotion_omits_substitute_line_when_none_exist() -> None:
    rendered = render_workflow_promotion(
        create_revision(),
    )

    assert "Substitute Models:" not in rendered


def test_render_workflow_promotion_does_not_present_revision_as_execution_authority() -> None:
    rendered = render_workflow_promotion(
        create_revision(),
    )

    assert "Active Revision" not in rendered
    assert "Execution Revision" not in rendered
    assert "Revision Pointer" not in rendered
