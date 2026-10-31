"""Tests for promoting an optimization experiment's winner (ADR 0092)."""

from uuid import UUID, uuid4, uuid5

import pytest

from azathoth.cli import (
    WorkflowExperimentNotFoundError,
    promote_configured_workflow,
)
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
)
from azathoth.runtime import AzathothRuntime
from azathoth.workflows import (
    InMemoryWorkflowExperimentRepository,
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    WorkflowCandidateRebuildError,
    WorkflowCandidateSignature,
    WorkflowCatalog,
    WorkflowExperimentCaseObservation,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowProductionRevision,
    WorkflowScorecard,
)
from tests.cli.test_promotion import (
    PRIMARY,
    STRATEGY_ID,
    WORKFLOW_ID,
    create_workflow,
)

REVISION = 2

CHEAP = FixedModelSelection(
    provider="test-provider",
    model="cheap",
)


def create_runtime(
    *,
    authorized: tuple[FixedModelSelection, ...] = (PRIMARY, CHEAP),
) -> AzathothRuntime:
    """Create a runtime at revision 2 with the primary and a cheap model."""

    models = (PRIMARY, CHEAP)

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(create_workflow(),),
            revisions={WORKFLOW_ID: REVISION},
        ),
        models=ModelCatalog(
            models=tuple(
                ModelMetadata(
                    provider=model.provider,
                    model=model.model,
                    display_name=model.identifier,
                )
                for model in models
            )
        ),
        portfolio=ModelPortfolio(
            entries=tuple(
                ModelPortfolioEntry(
                    provider=model.provider,
                    model=model.model,
                )
                for model in authorized
            )
        ),
        language_models=LanguageModelRegistry(
            {
                model.identifier: DeterministicLanguageModel(
                    provider=model.provider,
                    model=model.model,
                    response_text="success",
                )
                for model in models
            }
        ),
    )


def signature_on(
    model: FixedModelSelection,
    *,
    workflow_id: UUID = WORKFLOW_ID,
    revision: int = REVISION,
) -> WorkflowCandidateSignature:
    """Return the signature of the workflow's one prompt step on a model."""

    return WorkflowCandidateSignature(
        workflow_id=workflow_id,
        workflow_revision=revision,
        strategy_ids=(uuid5(STRATEGY_ID, model.identifier),),
    )


def create_observation(
    signature: WorkflowCandidateSignature,
    *,
    overall: float,
) -> WorkflowExperimentObservation:
    """Create one candidate observation with one judged case.

    The observed workflow is the one the signature names, as in a recorded
    experiment.
    """

    workflow = create_workflow().metadata.model_copy(
        update={"id": signature.workflow_id},
    )

    return WorkflowExperimentObservation(
        workflow=workflow,
        candidate_signature=signature,
        cases=(
            WorkflowExperimentCaseObservation(
                run_id=uuid4(),
                evaluation_id=uuid4(),
            ),
        ),
        scorecard=WorkflowScorecard(
            quality_score=1.0,
            reliability_score=1.0,
            latency_score=1.0,
            cost_score=overall,
            overall_score=overall,
        ),
    )


def create_experiment(
    winner: WorkflowCandidateSignature,
) -> WorkflowExperimentRecord:
    """Create an experiment whose winner beats the configured candidate."""

    winning = create_observation(winner, overall=0.9)
    configured = create_observation(signature_on(PRIMARY), overall=0.5)

    return WorkflowExperimentRecord(
        observations=(configured, winning),
        ranking=(winning.id, configured.id),
    )


def create_repository(
    *experiments: WorkflowExperimentRecord,
) -> InMemoryWorkflowExperimentRepository:
    """Create an experiment repository holding the experiments."""

    repository = InMemoryWorkflowExperimentRepository()

    for experiment in experiments:
        repository.save(experiment)

    return repository


def promote(
    *,
    experiment_id: UUID | None,
    experiments: InMemoryWorkflowExperimentRepository | None = None,
    runtime: AzathothRuntime | None = None,
    production_repository: InMemoryWorkflowProductionStateRepository | None = None,
    revision_repository: InMemoryWorkflowProductionRevisionRepository | None = None,
) -> WorkflowProductionRevision:
    """Promote the workflow, from an experiment when one is named."""

    return promote_configured_workflow(
        runtime=create_runtime() if runtime is None else runtime,
        workflow_id=WORKFLOW_ID,
        production_repository=(
            InMemoryWorkflowProductionStateRepository()
            if production_repository is None
            else production_repository
        ),
        revision_repository=(
            InMemoryWorkflowProductionRevisionRepository()
            if revision_repository is None
            else revision_repository
        ),
        experiment_id=experiment_id,
        experiment_repository=experiments,
    )


def promoted_model(
    revision: WorkflowProductionRevision,
) -> FixedModelSelection:
    """Return the model the promoted prompt step is pinned to."""

    step = revision.state.specification.steps[0].specification

    assert isinstance(step, PromptStrategySpec)
    assert isinstance(step.model_selection, FixedModelSelection)

    return step.model_selection


def test_promotion_without_an_experiment_pins_the_configured_model() -> None:
    assert promoted_model(promote(experiment_id=None)) == PRIMARY


def test_promotion_from_an_experiment_pins_the_winners_model() -> None:
    experiment = create_experiment(signature_on(CHEAP))

    revision = promote(
        experiment_id=experiment.id,
        experiments=create_repository(experiment),
    )

    assert promoted_model(revision) == CHEAP


def test_promotion_from_an_experiment_activates_the_winner() -> None:
    experiment = create_experiment(signature_on(CHEAP))
    production_repository = InMemoryWorkflowProductionStateRepository()

    revision = promote(
        experiment_id=experiment.id,
        experiments=create_repository(experiment),
        production_repository=production_repository,
    )

    assert production_repository.get(WORKFLOW_ID) == revision.state
    assert revision.state.specification_revision == REVISION


def test_promotion_from_an_experiment_whose_winner_is_configured() -> None:
    experiment = create_experiment(signature_on(PRIMARY))

    revision = promote(
        experiment_id=experiment.id,
        experiments=create_repository(experiment),
    )

    assert promoted_model(revision) == PRIMARY


def test_promotion_rejects_an_unknown_experiment() -> None:
    unknown = uuid4()
    production_repository = InMemoryWorkflowProductionStateRepository()
    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    with pytest.raises(
        WorkflowExperimentNotFoundError,
        match=f"^Experiment {unknown} was not found.$",
    ):
        promote(
            experiment_id=unknown,
            experiments=create_repository(),
            production_repository=production_repository,
            revision_repository=revision_repository,
        )

    assert production_repository.states() == ()
    assert revision_repository.revisions() == ()


def test_promotion_rejects_a_winner_measured_on_another_revision() -> None:
    experiment = create_experiment(signature_on(CHEAP, revision=1))
    production_repository = InMemoryWorkflowProductionStateRepository()

    with pytest.raises(
        WorkflowCandidateRebuildError,
        match="measured on revision 1 of workflow .*, but its current revision is 2",
    ):
        promote(
            experiment_id=experiment.id,
            experiments=create_repository(experiment),
            production_repository=production_repository,
        )

    assert production_repository.states() == ()


def test_promotion_rejects_a_winner_of_another_workflow() -> None:
    experiment = create_experiment(signature_on(CHEAP, workflow_id=uuid4()))

    with pytest.raises(
        WorkflowCandidateRebuildError,
        match=f"not workflow {WORKFLOW_ID}",
    ):
        promote(
            experiment_id=experiment.id,
            experiments=create_repository(experiment),
        )


def test_promotion_rejects_a_winner_whose_model_is_no_longer_authorized() -> None:
    experiment = create_experiment(signature_on(CHEAP))

    with pytest.raises(
        WorkflowCandidateRebuildError,
        match="cannot be rebuilt",
    ):
        promote(
            experiment_id=experiment.id,
            experiments=create_repository(experiment),
            runtime=create_runtime(authorized=(PRIMARY,)),
        )


def test_promotion_from_an_experiment_requires_an_experiment_repository() -> None:
    with pytest.raises(
        ValueError,
        match="requires an experiment repository",
    ):
        promote(experiment_id=uuid4())
