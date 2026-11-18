"""Rolling a workflow's production back to an earlier production revision (ADR 0128).

A rollback never edits history: it saves a new production revision whose
state is the earlier one's, and whose `restores` names it, and makes that
state active, so promotions and rollbacks are one timeline.
"""

from collections.abc import Callable
from uuid import UUID

from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    FixedModelSelection,
)
from azathoth.revisions import Author
from azathoth.workflows.production import (
    WorkflowProductionRevision,
    WorkflowProductionState,
)
from azathoth.workflows.production_inspection import active_production_revision
from azathoth.workflows.production_repository import WorkflowProductionStateRepository
from azathoth.workflows.production_revision_repository import (
    WorkflowProductionRevisionRepository,
)

ModelAuthorization = Callable[[str], bool]
"""Says whether the portfolio still authorizes a provider-qualified model."""


class WorkflowRollbackError(ValueError):
    """A workflow's production cannot be rolled back as asked; nothing changed."""


class NothingToRollBackToError(WorkflowRollbackError):
    """There is no earlier production revision, or the one named is already active."""


class WorkflowNotInProductionError(NothingToRollBackToError):
    """The workflow has no active production to roll back."""


class ProductionRevisionNotFoundError(WorkflowRollbackError):
    """The workflow has no production revision with the ID named."""


class RollbackModelNotAuthorizedError(WorkflowRollbackError):
    """A step of the state to restore has no model the portfolio still authorizes."""


def roll_back_workflow_production(
    *,
    workflow_id: UUID,
    repository: WorkflowProductionStateRepository,
    revision_repository: WorkflowProductionRevisionRepository,
    authorized: ModelAuthorization,
    to: UUID | None = None,
    author: Author | None = None,
) -> WorkflowProductionRevision:
    """Restore an earlier production revision's state as a new revision, and make it active.

    Without `to`, the revision restored is the newest made before the active
    one whose state differs from the active state, so rolling back twice
    undoes the first rollback. With `to`, it is that revision of this
    workflow. Every check is made before anything is written.

    Raises:
        WorkflowNotInProductionError: The workflow is not in production.
        NothingToRollBackToError: There is no earlier revision with another
            state, or the one named is already active.
        ProductionRevisionNotFoundError: This workflow has no revision `to`.
        RollbackModelNotAuthorizedError: A prompt step of the state to
            restore has neither its fixed model nor any approved substitute
            in the portfolio.
    """

    state = repository.get(workflow_id)

    if state is None:
        raise WorkflowNotInProductionError(f"Workflow {workflow_id} is not in production.")

    revisions = revision_repository.revisions_for_workflow(workflow_id)

    target = (
        _previous_revision(workflow_id, state, revisions)
        if to is None
        else _named_revision(workflow_id, state, revisions, to)
    )

    _require_authorized_models(target, authorized)

    restored = WorkflowProductionRevision(
        state=target.state,
        author=author,
        restores=target.id,
    )

    revision_repository.save(restored)
    repository.set(target.state)

    return restored


def _previous_revision(
    workflow_id: UUID,
    state: WorkflowProductionState,
    revisions: tuple[WorkflowProductionRevision, ...],
) -> WorkflowProductionRevision:
    """Return the newest revision made before the active one, with a state other than it."""

    active = active_production_revision(state, revisions)

    earlier = [
        revision
        for revision in revisions
        if revision.state != state and (active is None or revision.created_at < active.created_at)
    ]

    if not earlier:
        raise NothingToRollBackToError(
            f"Workflow {workflow_id} has no earlier production revision to roll back to."
        )

    return max(earlier, key=lambda revision: revision.created_at)


def _named_revision(
    workflow_id: UUID,
    state: WorkflowProductionState,
    revisions: tuple[WorkflowProductionRevision, ...],
    revision_id: UUID,
) -> WorkflowProductionRevision:
    """Return the workflow's revision with one ID, unless its state is already active."""

    named = next((revision for revision in revisions if revision.id == revision_id), None)

    if named is None:
        raise ProductionRevisionNotFoundError(
            f"Workflow {workflow_id} has no production revision {revision_id}."
        )

    if named.state == state:
        raise NothingToRollBackToError(
            f"Production revision {revision_id} is already active for workflow {workflow_id}."
        )

    return named


def _require_authorized_models(
    revision: WorkflowProductionRevision,
    authorized: ModelAuthorization,
) -> None:
    """Refuse a revision with a prompt step none of whose models the portfolio authorizes."""

    state = revision.state

    for step in state.specification.steps:
        specification = step.specification

        if not isinstance(specification, PROMPT_SPECIFICATIONS):
            continue

        primary = specification.model_selection

        if not isinstance(primary, FixedModelSelection):
            continue

        substitutes = next(
            (
                substitution.substitutes
                for substitution in state.model_substitutions
                if substitution.step_id == step.id
            ),
            (),
        )

        if any(authorized(model.identifier) for model in (primary, *substitutes)):
            continue

        raise RollbackModelNotAuthorizedError(
            f"Step {step.id} of production revision {revision.id} uses {primary.identifier}, "
            "which the portfolio no longer authorizes; authorize it again before rolling back "
            "to it."
        )


__all__ = [
    "ModelAuthorization",
    "NothingToRollBackToError",
    "ProductionRevisionNotFoundError",
    "RollbackModelNotAuthorizedError",
    "WorkflowNotInProductionError",
    "WorkflowRollbackError",
    "roll_back_workflow_production",
]
