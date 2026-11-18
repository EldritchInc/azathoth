"""Production through the service API: what runs, its history, promotion and rollback.

A workflow's production is its active `WorkflowProductionState` and the
production revisions that made each state active (ADR 0128). Promoting
builds a candidate from the workflow's latest revision, or rebuilds an
experiment's winner, and saves it as a new revision; rolling back saves an
earlier revision's state as a new one. Either records who did it.
"""

from uuid import UUID

from azathoth.api.authorship import AuthorAccess, author_view
from azathoth.api.browsing import LIMIT_MESSAGE, RepositoriesAccess
from azathoth.api.errors import (
    CandidateRebuildError,
    CandidateUnavailableError,
    ExperimentNotFoundError,
    InvalidArgumentError,
    ModelNotAuthorizedError,
    NotFoundError,
    NothingToRollBackToError,
    WorkflowResultMissingError,
)
from azathoth.api.models import (
    ProductionRevisionSummary,
    ProductionState,
    ProductionStepModels,
)
from azathoth.api.running import RuntimeAccess
from azathoth.persistence.repositories import Repositories
from azathoth.prompting import PROMPT_SPECIFICATIONS, FixedModelSelection
from azathoth.workflows import (
    NothingToRollBackToError as NothingEarlierError,
)
from azathoth.workflows import (
    ProductionRevisionNotFoundError,
    RollbackModelNotAuthorizedError,
    WorkflowCandidateRebuildError,
    WorkflowGenerationError,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowResultError,
    active_production_revision,
    promote_workflow_candidate,
    rebuild_workflow_candidate,
    roll_back_workflow_production,
)


class Production:
    """The production of an instance's workflows."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        runtime: RuntimeAccess,
        author: AuthorAccess,
    ) -> None:
        """Read and change production over `repositories`, promoting in `runtime`, as `author`."""

        self._repositories = repositories
        self._runtime = runtime
        self._author = author

    def get(
        self,
        workflow_id: UUID,
    ) -> ProductionState | None:
        """Return what a workflow's production runs now, or None when it is not in production.

        Only durable state is read, so no provider is reached.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: The workflow is neither configured nor has production history.
        """

        repositories = self._repositories()
        revisions = _known_history(repositories, workflow_id)
        state = repositories.production_states.get(workflow_id)

        if state is None:
            return None

        active = active_production_revision(state, revisions)

        return ProductionState(
            workflow_id=workflow_id,
            workflow_name=state.specification.metadata.name,
            workflow_revision=state.specification_revision,
            revision=_summary(active, active=True) if active is not None else None,
            steps=_steps(state),
            input_schema=state.specification.input_schema,
            output_schema=state.specification.output_schema,
            command=f"azathoth workflow production {workflow_id}",
        )

    def revisions(
        self,
        workflow_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[ProductionRevisionSummary, ...]:
        """Return a workflow's production revisions, newest first, the active one marked.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: The workflow is neither configured nor has production history.
        """

        if limit is not None and limit < 1:
            raise InvalidArgumentError(LIMIT_MESSAGE)

        repositories = self._repositories()
        revisions = _known_history(repositories, workflow_id)
        state = repositories.production_states.get(workflow_id)
        active = active_production_revision(state, revisions) if state is not None else None
        newest_first = sorted(revisions, key=lambda revision: revision.created_at, reverse=True)

        return tuple(
            _summary(revision, active=active is not None and revision.id == active.id)
            for revision in newest_first[:limit]
        )

    def promote(
        self,
        workflow_id: UUID,
        *,
        experiment_id: UUID | None = None,
    ) -> ProductionRevisionSummary:
        """Promote a workflow's latest revision, as `azathoth workflow promote` does.

        Without an experiment, the candidate a run would make is promoted.
        With one, the experiment's winner is rebuilt from the latest revision
        and promoted instead (ADR 0092). Every prompt step is pinned to the
        model chosen, and the new revision records who promoted.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidAuthorError: Who is promoting cannot be told.
            NotFoundError: The workflow is not configured.
            WorkflowResultMissingError: The workflow declares no result.
            ExperimentNotFoundError: No experiment has `experiment_id`.
            CandidateUnavailableError: No candidate could be made with the
                models authorized now.
            CandidateRebuildError: The experiment's winner cannot be rebuilt.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        author = self._author()
        repositories = self._repositories()
        runtime = self._runtime(repositories)
        specification = runtime.workflows.get(workflow_id)

        if specification is None:
            raise NotFoundError(f"Workflow {workflow_id} is not configured.")

        if specification.result is None:
            raise WorkflowResultMissingError(f"Workflow {workflow_id} does not declare a result.")

        try:
            candidate = runtime.generate_workflow_candidate(workflow_id)
        except WorkflowGenerationError as exc:
            raise CandidateUnavailableError(str(exc)) from exc

        if experiment_id is not None:
            experiment = repositories.experiments.get(experiment_id)

            if experiment is None:
                raise ExperimentNotFoundError(f"Experiment {experiment_id} was not found.")

            try:
                candidate = rebuild_workflow_candidate(
                    specification=specification,
                    configured=candidate,
                    signature=experiment.winner.candidate_signature,
                    catalog=runtime.models,
                    registry=runtime.language_models,
                    portfolio=runtime.portfolio,
                )
            except WorkflowCandidateRebuildError as exc:
                raise CandidateRebuildError(str(exc)) from exc

        try:
            revision = promote_workflow_candidate(
                specification=specification,
                candidate=candidate,
                repository=repositories.production_states,
                revision_repository=repositories.production_revisions,
                author=author,
            )
        except WorkflowResultError as exc:
            raise WorkflowResultMissingError(str(exc)) from exc

        return _summary(revision, active=True)

    def roll_back(
        self,
        workflow_id: UUID,
        *,
        to: UUID | None = None,
    ) -> ProductionRevisionSummary:
        """Restore an earlier production revision as a new one, as `workflow rollback` does.

        Without `to`, the newest revision before the active one with another
        state is restored. Only durable state is read, so no provider is
        reached; the portfolio decides whether its models may still run.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidAuthorError: Who is rolling back cannot be told.
            NotFoundError: The workflow is neither configured nor has
                production history, or has no production revision `to`.
            NothingToRollBackToError: It is not in production, has no
                earlier revision, or `to` is already active.
            ModelNotAuthorizedError: A prompt step of the state to restore
                has no model the portfolio authorizes.
        """

        author = self._author()
        repositories = self._repositories()

        _known_history(repositories, workflow_id)

        portfolio = repositories.portfolio

        try:
            revision = roll_back_workflow_production(
                workflow_id=workflow_id,
                repository=repositories.production_states,
                revision_repository=repositories.production_revisions,
                authorized=lambda identifier: portfolio.get(identifier) is not None,
                to=to,
                author=author,
            )
        except NothingEarlierError as exc:
            raise NothingToRollBackToError(str(exc)) from exc
        except ProductionRevisionNotFoundError as exc:
            raise NotFoundError(str(exc)) from exc
        except RollbackModelNotAuthorizedError as exc:
            raise ModelNotAuthorizedError(str(exc)) from exc

        return _summary(revision, active=True)


def _known_history(
    repositories: Repositories,
    workflow_id: UUID,
) -> tuple[WorkflowProductionRevision, ...]:
    """Return a workflow's production revisions, refusing one neither configured nor deployed.

    Raises:
        NotFoundError: The workflow is neither configured nor has production history.
    """

    revisions = repositories.production_revisions.revisions_for_workflow(workflow_id)

    if not revisions and not repositories.workflows.revisions(workflow_id):
        raise NotFoundError(f"Workflow {workflow_id} is not configured.")

    return revisions


def _summary(
    revision: WorkflowProductionRevision,
    *,
    active: bool,
) -> ProductionRevisionSummary:
    """Return the API's view of one production revision."""

    return ProductionRevisionSummary(
        revision_id=revision.id,
        workflow_id=revision.workflow_id,
        workflow_revision=revision.state.specification_revision,
        created_at=revision.created_at,
        author=author_view(revision.author),
        restores=revision.restores,
        active=active,
        steps=_steps(revision.state),
    )


def _steps(
    state: WorkflowProductionState,
) -> tuple[ProductionStepModels, ...]:
    """Return each prompt step's pinned model and approved substitutes, in workflow order."""

    substitutes = {
        substitution.step_id: substitution.substitutes for substitution in state.model_substitutions
    }

    return tuple(
        ProductionStepModels(
            step_id=step.id,
            primary=selection.identifier,
            substitutes=tuple(model.identifier for model in substitutes.get(step.id, ())),
        )
        for step in state.specification.steps
        if isinstance(step.specification, PROMPT_SPECIFICATIONS)
        and isinstance(selection := step.specification.model_selection, FixedModelSelection)
    )


__all__ = [
    "Production",
]
