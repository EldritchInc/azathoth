"""Tests that a run is scored on the citations its cited steps kept (ADR 0117)."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.evaluation import EvaluationResult, EvaluationStatus
from azathoth.prompting import CITATIONS_RESOURCE_KIND
from azathoth.strategies import (
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
    StrategyResourceBinding,
)
from azathoth.workflows import (
    CITED_RATIONALE,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunner,
    WorkflowScorecard,
    WorkflowScorer,
    WorkflowScoringPolicy,
    aggregate_workflow_scorecards,
    run_citation_score,
)

STEP_ID = UUID("c16b0000-0000-4000-8000-000000000001")


def counts(
    citations: int,
    verified: JsonValue = 0,
    verified_normalized: JsonValue = 0,
) -> StrategyResourceBinding:
    """Return a citations resource recording some counts, as a cited step's does."""

    return StrategyResourceBinding(
        kind=CITATIONS_RESOURCE_KIND,
        identifier=f"{citations:064x}",
        attributes={
            "citations": citations,
            "verified": verified,
            "verified_normalized": verified_normalized,
            "quote_not_found": 0,
            "unknown_segment": 0,
        },
    )


class KeepingStrategy:
    """A strategy recording some resources, and the cost a scored run needs."""

    def __init__(
        self,
        resources: tuple[StrategyResourceBinding, ...],
    ) -> None:
        self._resources = resources

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return StrategyMetadata(id=STEP_ID, name="cite", description="Cite.", version="1.0.0")

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Record the resources."""

        return StrategyOutcome(
            output="December 14",
            resources=self._resources,
            metrics=StrategyExecutionMetrics(estimated_cost_usd=0.0),
        )


def run_keeping(
    *resources: StrategyResourceBinding,
) -> WorkflowRun:
    """Run one step recording some resources; return the run."""

    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=UUID("c16b0000-0000-4000-8000-000000000002"),
            name="cite",
            description="Cite.",
            version="1.0.0",
        ),
        steps=(WorkflowCandidateStep(id=STEP_ID, strategy=KeepingStrategy(resources)),),
    )

    return asyncio.run(WorkflowRunner().run_recording_failures(candidate, Context()))


def test_a_run_with_no_cited_step_has_no_citation_score() -> None:
    assert run_citation_score(run_keeping()) is None
    assert (
        run_citation_score(run_keeping(StrategyResourceBinding(kind="model", identifier="m")))
        is None
    )


def test_a_runs_citation_score_is_its_verified_citations_over_all() -> None:
    assert run_citation_score(run_keeping(counts(4, 2, 1))) == pytest.approx(0.75)


def test_every_record_of_a_run_counts_together() -> None:
    assert run_citation_score(
        run_keeping(counts(3, 3), StrategyResourceBinding(kind="model", identifier="m"), counts(1))
    ) == pytest.approx(0.75)


def test_a_cited_step_that_cited_nothing_scores_zero() -> None:
    assert run_citation_score(run_keeping(counts(0))) == 0.0


@pytest.mark.parametrize(
    "verified",
    [
        pytest.param(True, id="a-boolean"),
        pytest.param(-2, id="negative"),
        pytest.param("2", id="a-string"),
    ],
)
def test_a_count_that_is_not_one_counts_nothing(
    verified: JsonValue,
) -> None:
    assert run_citation_score(run_keeping(counts(2, verified, 1))) == pytest.approx(0.5)


def test_a_record_counting_more_verified_than_citations_scores_at_most_one() -> None:
    assert run_citation_score(run_keeping(counts(1, 2))) == 1.0


def evaluation() -> EvaluationResult:
    """Return a passing evaluation."""

    return EvaluationResult(
        evaluator_name="exact-match",
        score=1.0,
        status=EvaluationStatus.PASSED,
        reason="Matched.",
    )


def scored(
    run: WorkflowRun,
) -> WorkflowScorecard:
    """Score one run against generous targets."""

    return WorkflowScorer(
        policy=WorkflowScoringPolicy(target_latency_seconds=60.0, target_cost_usd=1.0)
    ).score(run=run, evaluation=evaluation())


def test_a_cited_run_is_scored_on_five_dimensions() -> None:
    scorecard = scored(run_keeping(counts(2, 1)))

    assert scorecard.citation_score == 0.5
    assert scorecard.overall_score == pytest.approx(
        (
            scorecard.quality_score
            + scorecard.reliability_score
            + scorecard.latency_score
            + scorecard.cost_score
            + 0.5
        )
        / 5.0
    )
    assert scorecard.rationale == CITED_RATIONALE


def test_a_run_with_no_cited_step_is_scored_on_four_as_it_always_was() -> None:
    scorecard = scored(run_keeping())

    assert scorecard.citation_score is None
    assert scorecard.overall_score == pytest.approx(
        (
            scorecard.quality_score
            + scorecard.reliability_score
            + scorecard.latency_score
            + scorecard.cost_score
        )
        / 4.0
    )
    assert scorecard.rationale == (
        "Canonical workflow score calculated from quality, reliability, latency, and cost."
    )


def test_the_cited_rationale_names_citations() -> None:
    assert CITED_RATIONALE == (
        "Canonical workflow score calculated from quality, reliability, latency, cost, and "
        "citations."
    )


def scorecard(
    citation_score: float | None,
) -> WorkflowScorecard:
    """Return a scorecard with some citation score."""

    return WorkflowScorecard(
        quality_score=1.0,
        reliability_score=1.0,
        latency_score=1.0,
        cost_score=1.0,
        citation_score=citation_score,
        overall_score=1.0,
    )


def test_aggregated_citation_scores_are_the_mean_of_those_present() -> None:
    aggregated = aggregate_workflow_scorecards(
        (scorecard(0.5), scorecard(None), scorecard(1.0)), rationale="r"
    )

    assert aggregated.citation_score == pytest.approx(0.75)


def test_scorecards_with_no_citation_score_aggregate_to_none() -> None:
    assert (
        aggregate_workflow_scorecards(
            (scorecard(None), scorecard(None)), rationale="r"
        ).citation_score
        is None
    )


def test_a_scorecard_names_its_citation_score_only_when_it_has_one() -> None:
    assert scorecard(0.5).model_dump(mode="json")["citation_score"] == 0.5
    assert "citation_score" not in scorecard(None).model_dump(mode="json")
    assert WorkflowScorecard.model_validate(scorecard(None).model_dump(mode="json")) == scorecard(
        None
    )
