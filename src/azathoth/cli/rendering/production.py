"""Human-readable workflow production state and revision rendering."""

from collections.abc import Iterable
from uuid import UUID

from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    FixedModelSelection,
)
from azathoth.workflows import (
    WorkflowProductionRevision,
    WorkflowProductionState,
    describe_value_reference,
)

ACTIVE_REVISION_MARKER = "active"
INACTIVE_REVISION_MARKER = "-"


def render_workflow_production(
    state: WorkflowProductionState,
    *,
    active_revision: WorkflowProductionRevision | None,
) -> str:
    """Render the active production configuration of one workflow."""

    workflow = state.specification.metadata

    lines = [
        f"Workflow: {workflow.name}",
        f"Workflow ID: {workflow.id}",
        "Revision ID: "
        + (str(active_revision.id) if active_revision is not None else "unrecorded"),
        "Deployed At: "
        + (active_revision.created_at.isoformat() if active_revision is not None else "unknown"),
    ]

    for step_id, primary in _primary_models(state):
        lines.extend(
            (
                "",
                f"Prompt Step: {step_id}",
                f"Primary Model: {primary}",
            )
        )

        substitution = next(
            (candidate for candidate in state.model_substitutions if candidate.step_id == step_id),
            None,
        )

        if substitution is not None:
            lines.append(
                "Substitute Models: "
                + ", ".join(model.identifier for model in substitution.substitutes)
            )

    if state.emissions:
        lines.append("")

        lines.extend(
            (f"Emission: {emission.name} <- {describe_value_reference(emission.source)}")
            for emission in state.emissions
        )

    return "\n".join(lines)


def render_workflow_revision_summaries(
    revisions: Iterable[WorkflowProductionRevision],
    *,
    active_revision_id: UUID | None,
) -> str:
    """Render one line per production revision in the order given.

    Each line contains the revision ID, creation time, an active marker, and
    the primary model of every prompt step.
    """

    return "\n".join(
        _render_revision_summary(
            revision,
            active=revision.id == active_revision_id,
        )
        for revision in revisions
    )


def _render_revision_summary(
    revision: WorkflowProductionRevision,
    *,
    active: bool,
) -> str:
    """Render one aligned production revision summary line."""

    marker = ACTIVE_REVISION_MARKER if active else INACTIVE_REVISION_MARKER
    models = ", ".join(primary for _step_id, primary in _primary_models(revision.state))

    return (
        f"{revision.id}  {revision.created_at.isoformat()}  {marker:<6}  "
        f"{models or 'no prompt steps'}"
    )


def _primary_models(
    state: WorkflowProductionState,
) -> tuple[tuple[UUID, str], ...]:
    """Return each prompt step's primary model in specification order."""

    primaries: list[tuple[UUID, str]] = []

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

        primaries.append((step.id, selection.identifier))

    return tuple(primaries)
