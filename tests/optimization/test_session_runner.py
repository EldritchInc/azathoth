"""Tests for workflow optimization session orchestration."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.optimization import (
    ReplayWorkflowOptimizer,
    WorkflowOptimizationResult,
    WorkflowOptimizationSessionRunner,
)
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    RankedWorkflow,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
    WorkflowMetadata,
    WorkflowRanking,
    WorkflowScorecard,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")
DATASET_ID = UUID("77777777-7777-7777-7777-777777777777")
PROPOSED_STEP_ID = UUID("88888888-8888-8888-8888-888888888888")


class StaticStrategy:
    """Return one deterministic strategy outcome."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=f"strategy-{strategy_id}",
            description="Deterministic session runner strategy.",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Return a deterministic strategy outcome."""

        return StrategyOutcome(
            output="success",
        )


class RecordingExperimentRunner:
    """Record candidate populations supplied to workflow experiments."""

    def __init__(self) -> None:
        self.candidate_populations: list[tuple[WorkflowCandidate, ...]] = []
        self.datasets: list[BenchmarkDataset] = []

    async def run(
        self,
        *,
        workflows: tuple[WorkflowCandidate, ...],
        dataset: BenchmarkDataset,
    ) -> WorkflowExperimentResult:
        """Record a population and return deterministic experiment evidence."""

        self.candidate_populations.append(workflows)
        self.datasets.append(dataset)

        winner = create_scorecard(
            overall_score=0.9,
        )
        runner_up = create_scorecard(
            overall_score=0.7,
        )

        candidates = create_candidates()

        return WorkflowExperimentResult(
            evidence=(
                WorkflowExperimentEvidence(
                    candidate_signature=candidates[0].signature,
                    scorecard=winner,
                ),
                WorkflowExperimentEvidence(
                    candidate_signature=candidates[1].signature,
                    scorecard=runner_up,
                ),
            ),
            ranking=WorkflowRanking(
                entries=(
                    RankedWorkflow(
                        rank=1,
                        scorecard=winner,
                    ),
                    RankedWorkflow(
                        rank=2,
                        scorecard=runner_up,
                    ),
                ),
            ),
        )


class RecordingOptimizer:
    """Record optimizer calls while reversing each candidate population."""

    def __init__(self) -> None:
        self.generations: list[int] = []
        self.candidate_populations: list[tuple[WorkflowCandidate, ...]] = []

    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult:
        """Record the call and return the reversed population."""

        self.generations.append(generation)
        self.candidate_populations.append(candidates)

        return WorkflowOptimizationResult(
            generation=generation,
            previous_experiment=experiment,
            candidates=tuple(reversed(candidates)),
        )


class PopulationExperimentRunner:
    """Score whatever population it receives, the last candidate highest."""

    def __init__(self) -> None:
        self.candidate_populations: list[tuple[WorkflowCandidate, ...]] = []
        self.datasets: list[BenchmarkDataset] = []

    async def run(
        self,
        *,
        workflows: tuple[WorkflowCandidate, ...],
        dataset: BenchmarkDataset,
    ) -> WorkflowExperimentResult:
        """Record a population and rank its last candidate first."""

        self.candidate_populations.append(workflows)
        self.datasets.append(dataset)

        scorecards = tuple(
            create_scorecard(
                overall_score=(index + 1) / (len(workflows) + 1),
            )
            for index in range(len(workflows))
        )

        return WorkflowExperimentResult(
            evidence=tuple(
                WorkflowExperimentEvidence(
                    candidate_signature=candidate.signature,
                    scorecard=scorecard,
                )
                for candidate, scorecard in zip(workflows, scorecards, strict=True)
            ),
            ranking=WorkflowRanking(
                entries=tuple(
                    RankedWorkflow(
                        rank=rank,
                        scorecard=scorecard,
                    )
                    for rank, scorecard in enumerate(reversed(scorecards), start=1)
                ),
            ),
        )


class ProposingOptimizer:
    """Propose one new candidate per generation, keeping the population."""

    def __init__(self) -> None:
        self.generations: list[int] = []

    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult:
        """Return the population with one new candidate appended."""

        self.generations.append(generation)

        return WorkflowOptimizationResult(
            generation=generation,
            previous_experiment=experiment,
            candidates=(*candidates, create_proposed_candidate(generation)),
        )


def create_proposed_candidate(
    generation: int,
) -> WorkflowCandidate:
    """Create the distinct candidate a generation proposes."""

    return create_candidate(
        workflow_id=UUID(int=generation),
        step_id=PROPOSED_STEP_ID,
        strategy_id=UUID(int=1000 + generation),
    )


def create_candidate(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
) -> WorkflowCandidate:
    """Create a deterministic workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow-{workflow_id}",
            description="Workflow optimization session candidate.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=step_id,
                strategy=StaticStrategy(
                    strategy_id=strategy_id,
                ),
            ),
        ),
    )


def create_candidates() -> tuple[WorkflowCandidate, ...]:
    """Create a deterministic candidate population."""

    return (
        create_candidate(
            workflow_id=WORKFLOW_ID,
            step_id=STEP_ID,
            strategy_id=STRATEGY_ID,
        ),
        create_candidate(
            workflow_id=SECOND_WORKFLOW_ID,
            step_id=SECOND_STEP_ID,
            strategy_id=SECOND_STRATEGY_ID,
        ),
    )


def create_scorecard(
    *,
    overall_score: float,
) -> WorkflowScorecard:
    """Create a deterministic workflow scorecard."""

    return WorkflowScorecard(
        quality_score=overall_score,
        reliability_score=overall_score,
        latency_score=overall_score,
        cost_score=overall_score,
        overall_score=overall_score,
    )


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic one-case benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="session-runner",
        description="Benchmark used for session runner tests.",
        cases=(
            BenchmarkCase(
                input="request",
                expected=ExpectedOutcome(
                    description="Workflow should return success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def test_session_runner_records_requested_generations() -> None:
    """Session runner should produce every requested generation."""

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=RecordingExperimentRunner(),
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=3,
        )
    )

    assert tuple(generation.generation for generation in session.generations) == (
        1,
        2,
        3,
    )


def test_session_runner_preserves_initial_candidates() -> None:
    """Session history should preserve the original candidate population."""

    candidates = create_candidates()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=RecordingExperimentRunner(),
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=candidates,
            dataset=create_dataset(),
            max_generations=2,
        )
    )

    assert session.initial_candidates == candidates
    assert session.initial_candidates[0] is candidates[0]
    assert session.initial_candidates[1] is candidates[1]


def test_session_runner_experiments_on_each_generation_population() -> None:
    """Each experiment should receive the population produced previously."""

    candidates = create_candidates()
    experiment_runner = RecordingExperimentRunner()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=candidates,
            dataset=create_dataset(),
            max_generations=3,
        )
    )

    assert len(experiment_runner.candidate_populations) == 3
    assert experiment_runner.candidate_populations[0] == candidates
    assert experiment_runner.candidate_populations[1] == session.generations[0].candidates
    assert experiment_runner.candidate_populations[2] == session.generations[1].candidates


def test_session_runner_records_experiment_for_each_generation() -> None:
    """Each optimization generation should retain its preceding experiment."""

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=RecordingExperimentRunner(),
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=2,
        )
    )

    assert len(session.generations) == 2
    assert session.generations[0].previous_experiment.winner.overall_score == 0.9
    assert session.generations[1].previous_experiment.winner.overall_score == 0.9


def test_session_runner_rejects_zero_generations() -> None:
    """Optimization sessions must execute at least one generation."""

    with pytest.raises(
        ValueError,
        match="Workflow optimization sessions require at least one generation.",
    ):
        asyncio.run(
            WorkflowOptimizationSessionRunner(
                experiment_runner=RecordingExperimentRunner(),
                optimizer=ReplayWorkflowOptimizer(),
            ).run(
                initial_candidates=create_candidates(),
                dataset=create_dataset(),
                max_generations=0,
            )
        )


def test_session_runner_rejects_negative_generations() -> None:
    """Optimization session generation limits cannot be negative."""

    with pytest.raises(
        ValueError,
        match="Workflow optimization sessions require at least one generation.",
    ):
        asyncio.run(
            WorkflowOptimizationSessionRunner(
                experiment_runner=RecordingExperimentRunner(),
                optimizer=ReplayWorkflowOptimizer(),
            ).run(
                initial_candidates=create_candidates(),
                dataset=create_dataset(),
                max_generations=-1,
            )
        )


def test_session_runner_calls_optimizer_for_each_generation() -> None:
    """Every experiment should be followed by one optimizer invocation."""

    optimizer = RecordingOptimizer()

    asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=RecordingExperimentRunner(),
            optimizer=optimizer,
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=3,
        )
    )

    assert optimizer.generations == [
        1,
        2,
        3,
    ]
    assert len(optimizer.candidate_populations) == 3


def test_session_runner_propagates_transformed_candidate_populations() -> None:
    """Optimizer output should become the next experiment population."""

    candidates = create_candidates()
    experiment_runner = RecordingExperimentRunner()
    optimizer = RecordingOptimizer()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=optimizer,
        ).run(
            initial_candidates=candidates,
            dataset=create_dataset(),
            max_generations=3,
        )
    )

    reversed_candidates = tuple(reversed(candidates))

    assert experiment_runner.candidate_populations == [
        candidates,
        reversed_candidates,
        candidates,
    ]

    assert session.generations[0].candidates == reversed_candidates
    assert session.generations[1].candidates == candidates
    assert session.generations[2].candidates == reversed_candidates


def test_session_runner_passes_current_population_to_optimizer() -> None:
    """Optimizer input should match the population that was just experimented on."""

    candidates = create_candidates()
    optimizer = RecordingOptimizer()

    asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=RecordingExperimentRunner(),
            optimizer=optimizer,
        ).run(
            initial_candidates=candidates,
            dataset=create_dataset(),
            max_generations=3,
        )
    )

    assert optimizer.candidate_populations == [
        candidates,
        tuple(reversed(candidates)),
        candidates,
    ]


def test_session_runner_stops_at_requested_generation_limit() -> None:
    """Session orchestration should stop exactly at the configured limit."""

    experiment_runner = RecordingExperimentRunner()
    optimizer = RecordingOptimizer()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=optimizer,
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=4,
        )
    )

    assert len(session.generations) == 4
    assert len(experiment_runner.candidate_populations) == 4
    assert optimizer.generations == [
        1,
        2,
        3,
        4,
    ]


def test_session_runner_is_deterministic() -> None:
    """Equivalent runs should produce equivalent optimization histories.

    Every experiment is a distinct execution with its own identity, so
    determinism is asserted over everything except experiment identity.
    """

    candidates = create_candidates()

    first = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=RecordingExperimentRunner(),
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=candidates,
            dataset=create_dataset(),
            max_generations=3,
        )
    )

    second = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=RecordingExperimentRunner(),
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=candidates,
            dataset=create_dataset(),
            max_generations=3,
        )
    )

    assert first.initial_candidates == second.initial_candidates
    assert len(first.generations) == len(second.generations)

    for first_generation, second_generation in zip(
        first.generations,
        second.generations,
        strict=True,
    ):
        assert first_generation.generation == second_generation.generation
        assert first_generation.candidates == second_generation.candidates
        assert first_generation.previous_experiment.evidence == (
            second_generation.previous_experiment.evidence
        )
        assert first_generation.previous_experiment.ranking == (
            second_generation.previous_experiment.ranking
        )

    experiment_ids = [
        generation.previous_experiment.id
        for session in (first, second)
        for generation in session.generations
    ]

    assert len(experiment_ids) == len(set(experiment_ids))


def test_session_runner_judges_every_generation_on_the_same_benchmark() -> None:
    """Every generation's experiment receives the session's benchmark dataset."""

    dataset = create_dataset()
    experiment_runner = RecordingExperimentRunner()

    asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=create_candidates(),
            dataset=dataset,
            max_generations=3,
        )
    )

    assert experiment_runner.datasets == [
        dataset,
        dataset,
        dataset,
    ]


def test_session_runner_evaluates_the_final_proposals() -> None:
    """One generation measures the population it proposed."""

    candidates = create_candidates()
    experiment_runner = PopulationExperimentRunner()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=ProposingOptimizer(),
        ).run(
            initial_candidates=candidates,
            dataset=create_dataset(),
            max_generations=1,
        )
    )

    assert experiment_runner.candidate_populations == [
        candidates,
        session.generations[0].candidates,
    ]

    assert session.final_experiment is not None
    assert len(session.final_experiment.evidence) == 3


def test_session_runner_final_proposal_can_win() -> None:
    """The session's winner may be a candidate only the final evaluation measured."""

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=PopulationExperimentRunner(),
            optimizer=ProposingOptimizer(),
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=1,
        )
    )

    assert session.winning_experiment == session.final_experiment
    assert session.winner is not None
    assert session.winner.metadata.id == UUID(int=1)


def test_session_runner_evaluates_only_the_last_generations_proposals() -> None:
    """Earlier proposals are measured by the next generation, not again at the end."""

    experiment_runner = PopulationExperimentRunner()
    optimizer = ProposingOptimizer()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=optimizer,
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=2,
        )
    )

    assert len(experiment_runner.candidate_populations) == 3
    assert experiment_runner.candidate_populations[-1] == session.generations[-1].candidates
    assert optimizer.generations == [
        1,
        2,
    ]

    assert session.final_experiment is not None
    assert session.final_experiment.id not in {
        generation.previous_experiment.id for generation in session.generations
    }


def test_session_runner_skips_the_final_evaluation_when_nothing_is_new() -> None:
    """A population the last experiment already measured is not run again."""

    experiment_runner = RecordingExperimentRunner()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=2,
        )
    )

    assert session.final_experiment is None
    assert len(experiment_runner.candidate_populations) == 2
    assert session.winning_experiment == session.generations[-1].previous_experiment


def test_session_runner_skips_the_final_evaluation_for_a_reordered_population() -> None:
    """Reordering evaluated candidates proposes nothing new."""

    experiment_runner = RecordingExperimentRunner()

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=RecordingOptimizer(),
        ).run(
            initial_candidates=create_candidates(),
            dataset=create_dataset(),
            max_generations=1,
        )
    )

    assert session.final_experiment is None
    assert len(experiment_runner.candidate_populations) == 1


def test_session_runner_judges_the_final_evaluation_on_the_same_benchmark() -> None:
    """The final evaluation receives the session's benchmark dataset."""

    dataset = create_dataset()
    experiment_runner = PopulationExperimentRunner()

    asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=ProposingOptimizer(),
        ).run(
            initial_candidates=create_candidates(),
            dataset=dataset,
            max_generations=1,
        )
    )

    assert experiment_runner.datasets == [
        dataset,
        dataset,
    ]
