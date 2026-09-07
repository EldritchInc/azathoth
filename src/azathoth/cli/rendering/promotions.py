"""Human-readable workflow production promotion rendering."""

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.workflows import WorkflowProductionRevision


def render_workflow_promotion(
    revision: WorkflowProductionRevision,
) -> str:
    """Render one completed workflow production promotion."""

    state = revision.state
    workflow = state.specification.metadata

    lines = [
        f"Workflow: {workflow.name}",
        f"Workflow ID: {workflow.id}",
        f"Revision ID: {revision.id}",
        "Status: promoted",
        f"Created At: {revision.created_at.isoformat()}",
    ]

    for step in state.specification.steps:
        specification = step.specification

        if not isinstance(
            specification,
            PromptStrategySpec,
        ):
            continue

        selection = specification.model_selection

        assert isinstance(
            selection,
            FixedModelSelection,
        )

        lines.extend(
            (
                "",
                f"Prompt Step: {step.id}",
                f"Primary Model: {selection.identifier}",
            )
        )

        substitution = next(
            (candidate for candidate in state.model_substitutions if candidate.step_id == step.id),
            None,
        )

        if substitution is not None:
            lines.append(
                "Substitute Models: "
                + ", ".join(model.identifier for model in substitution.substitutes)
            )

    return "\n".join(lines)
