"""Application services for promoting configured workflows."""

from uuid import UUID

from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowExperimentRepository,
    WorkflowProductionModelSubstitution,
    WorkflowProductionRevision,
    WorkflowProductionRevisionRepository,
    WorkflowProductionStateRepository,
    promote_workflow_candidate,
    rebuild_workflow_candidate,
)


class WorkflowExperimentNotFoundError(LookupError):
    """Raised when promotion names an experiment that was never recorded."""


def promote_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    production_repository: WorkflowProductionStateRepository,
    revision_repository: WorkflowProductionRevisionRepository,
    model_substitutions: tuple[WorkflowProductionModelSubstitution, ...] = (),
    experiment_id: UUID | None = None,
    experiment_repository: WorkflowExperimentRepository | None = None,
) -> WorkflowProductionRevision:
    """Promote one configured workflow's candidate to production.

    Without an experiment, the configured candidate is promoted. With one,
    the experiment's top-ranked candidate is rebuilt from the workflow's
    current revision and promoted instead (ADR 0092).

    Raises:
        WorkflowNotConfiguredError: The workflow is not configured.
        WorkflowExperimentNotFoundError: The named experiment was not
            recorded.
        WorkflowCandidateRebuildError: The experiment's winner is another
            workflow or revision, or cannot be rebuilt with the currently
            authorized models.
        WorkflowResultError: The workflow does not declare a result.
    """

    candidate = runtime.generate_workflow_candidate(
        workflow_id,
    )

    specification = runtime.workflows.get(
        workflow_id,
    )

    assert specification is not None

    if experiment_id is not None:
        if experiment_repository is None:
            raise ValueError("Promoting an experiment's winner requires an experiment repository.")

        experiment = experiment_repository.get(
            experiment_id,
        )

        if experiment is None:
            raise WorkflowExperimentNotFoundError(f"Experiment {experiment_id} was not found.")

        candidate = rebuild_workflow_candidate(
            specification=specification,
            configured=candidate,
            signature=experiment.winner.candidate_signature,
            catalog=runtime.models,
            registry=runtime.language_models,
            portfolio=runtime.portfolio,
        )

    return promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=production_repository,
        revision_repository=revision_repository,
        model_substitutions=model_substitutions,
    )
