"""Human-readable workflow production promotion rendering."""

from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    FixedModelSelection,
)
from azathoth.workflows import WorkflowProductionRevision


def render_workflow_promotion(
    revision: WorkflowProductionRevision,
) -> str:
    """Render one completed workflow production promotion."""

    return _render_deployment(revision, status="promoted")


def render_workflow_rollback(
    revision: WorkflowProductionRevision,
) -> str:
    """Render one completed rollback: the new revision, and the one it restored (ADR 0128)."""

    return _render_deployment(revision, status="rolled back")


def _render_deployment(
    revision: WorkflowProductionRevision,
    *,
    status: str,
) -> str:
    """Render one new production revision, its status, and its prompt steps' models."""

    state = revision.state
    workflow = state.specification.metadata

    lines = [
        f"Workflow: {workflow.name}",
        f"Workflow ID: {workflow.id}",
        f"Revision ID: {revision.id}",
        f"Status: {status}",
    ]

    if revision.restores is not None:
        lines.append(f"Restores: {revision.restores}")

    lines.extend(
        (
            f"Author: {revision.author}" if revision.author is not None else "Author: unknown",
            f"Created At: {revision.created_at.isoformat()}",
        )
    )

    for step in state.specification.steps:
        specification = step.specification

        if not isinstance(
            specification,
            PROMPT_SPECIFICATIONS,
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
