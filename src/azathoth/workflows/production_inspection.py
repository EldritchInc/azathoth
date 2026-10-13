"""Read-only inspection of durable workflow production history."""

from collections.abc import Iterable

from azathoth.workflows.production import (
    WorkflowProductionRevision,
    WorkflowProductionState,
)


def active_production_revision(
    state: WorkflowProductionState,
    revisions: Iterable[WorkflowProductionRevision],
) -> WorkflowProductionRevision | None:
    """Return the revision that deployed the active production state.

    Production state records only what is active, while revisions record every
    deployment. The active revision is the newest revision of the same workflow
    whose state equals the active state; a later revision wins a timestamp tie.
    None means the active state was set without a recorded revision.
    """

    workflow_id = state.specification.metadata.id

    active: WorkflowProductionRevision | None = None

    for revision in revisions:
        if revision.workflow_id != workflow_id or revision.state != state:
            continue

        if active is None or revision.created_at >= active.created_at:
            active = revision

    return active


__all__ = [
    "active_production_revision",
]
