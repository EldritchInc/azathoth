"""Application services for promoting configured workflows."""

from uuid import UUID

from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowProductionModelSubstitution,
    WorkflowProductionRevision,
    WorkflowProductionRevisionRepository,
    WorkflowProductionStateRepository,
    promote_workflow_candidate,
)


def promote_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    production_repository: WorkflowProductionStateRepository,
    revision_repository: WorkflowProductionRevisionRepository,
    model_substitutions: tuple[WorkflowProductionModelSubstitution, ...] = (),
) -> WorkflowProductionRevision:
    """Promote one configured workflow's generated candidate to production."""

    candidate = runtime.generate_workflow_candidate(
        workflow_id,
    )

    specification = runtime.workflows.get(
        workflow_id,
    )

    assert specification is not None

    return promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=production_repository,
        revision_repository=revision_repository,
        model_substitutions=model_substitutions,
    )
