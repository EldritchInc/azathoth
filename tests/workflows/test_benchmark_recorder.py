"""Tests for durable recording of benchmark runs and comparisons."""

import asyncio
from uuid import UUID

import pytest

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeComparison,
)
from azathoth.workflows import (
    InMemoryWorkflowBenchmarkExecutionRepository,
    InMemoryWorkflowRunEvaluationRepository,
    InMemoryWorkflowRunRepository,
    WorkflowBenchmarkComparator,
    WorkflowBenchmarkComparison,
    WorkflowBenchmarkEvidenceRecorder,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkRanker,
    WorkflowBenchmarkRanking,
    WorkflowBenchmarkResult,
    WorkflowBenchmarkScorer,
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowScoringPolicy,
)
from tests.evaluation.test_semantic import (
    PASS_REPLY,
    ScriptedJudgeModel,
)
from tests.workflows.test_benchmark_run_failures import (
    FAILING_CASE_ID,
    create_single_step_candidate,
    create_tolerant_candidate,
)
from tests.workflows.test_benchmark_semantic import (
    DATASET_ID,
    EXACT_CASE_ID,
    JUDGE_COST_USD,
    SEMANTIC_CASE_ID,
    create_dataset,
    create_runner,
)

POLICY = WorkflowScoringPolicy(
    target_latency_seconds=10.0,
    target_cost_usd=0.01,
)


def create_recorder() -> WorkflowBenchmarkEvidenceRecorder:
    """Create a recorder over empty in-memory repositories."""

    return WorkflowBenchmarkEvidenceRecorder(
        runs=InMemoryWorkflowRunRepository(),
        evaluations=InMemoryWorkflowRunEvaluationRepository(),
        executions=InMemoryWorkflowBenchmarkExecutionRepository(),
    )


def first_case(
    dataset: BenchmarkDataset,
) -> BenchmarkCase:
    """Return the first case of one dataset."""

    return dataset.cases[0]


def run_tolerant_benchmark() -> tuple[WorkflowBenchmarkResult, WorkflowCandidate]:
    """Run the exact-plus-semantic benchmark with one judged pass.

    The tolerant candidate's helper step fails on every case without blocking
    its answer, so every case is judged on its result.
    """

    dataset = create_dataset()
    candidate = create_tolerant_candidate(first_case(dataset))

    result = asyncio.run(
        create_runner(
            ScriptedJudgeModel(
                PASS_REPLY,
                cost_usd=JUDGE_COST_USD,
            )
        ).run(
            dataset,
            lambda _case: candidate,
        )
    )

    return result, candidate


def run_comparison() -> tuple[
    WorkflowBenchmarkComparison,
    WorkflowBenchmarkRanking,
    dict[str, WorkflowCandidate],
]:
    """Compare a tolerant candidate with one whose second run fails.

    The second case is the failing case, judged semantically, so the tolerant
    candidate is judged once and the fragile candidate's failed run is never
    judged.
    """

    dataset = create_dataset(
        semantic_case_id=FAILING_CASE_ID,
    )

    candidates = {
        "tolerant": create_tolerant_candidate(first_case(dataset)),
        "fragile": create_single_step_candidate(first_case(dataset)),
    }

    comparator = WorkflowBenchmarkComparator(
        runner=create_runner(
            ScriptedJudgeModel(
                PASS_REPLY,
                cost_usd=JUDGE_COST_USD,
            )
        ),
    )

    comparison = asyncio.run(
        comparator.compare(
            dataset,
            {
                "tolerant": lambda _case: candidates["tolerant"],
                "fragile": create_single_step_candidate,
            },
        )
    )

    ranking = WorkflowBenchmarkRanker(
        scorer=WorkflowBenchmarkScorer(
            policy=POLICY,
        ),
    ).rank(comparison)

    return comparison, ranking, candidates


def test_benchmark_results_have_distinct_identities() -> None:
    """Every benchmark result is identified, so its record can share the identity."""

    first = WorkflowBenchmarkResult(dataset_id=DATASET_ID)
    second = WorkflowBenchmarkResult(dataset_id=DATASET_ID)

    assert first.id != second.id


def test_benchmark_result_identity_survives_json() -> None:
    """A result keeps its identity through JSON."""

    result, _candidate = run_tolerant_benchmark()

    restored = WorkflowBenchmarkResult.model_validate_json(
        result.model_dump_json(),
    )

    assert restored.id == result.id


def test_benchmark_rankings_have_distinct_identities() -> None:
    """Every ranking is identified, so its record can share the identity."""

    comparison, ranking, _candidates = run_comparison()

    again = WorkflowBenchmarkRanker(
        scorer=WorkflowBenchmarkScorer(
            policy=POLICY,
        ),
    ).rank(comparison)

    assert ranking.id != again.id


def test_case_results_report_run_failures_and_judge_totals() -> None:
    """Case results expose the facts their durable record keeps."""

    comparison, _ranking, _candidates = run_comparison()

    tolerant = comparison.get("tolerant")
    fragile = comparison.get("fragile")

    assert tolerant is not None
    assert fragile is not None

    assert tuple(case.run_failure for case in tolerant.cases) == (False, False)
    assert tuple(case.judge_calls for case in tolerant.cases) == (0, 1)
    assert tolerant.cases[1].judge_cost_usd == pytest.approx(JUDGE_COST_USD)

    assert tuple(case.run_failure for case in fragile.cases) == (False, True)
    assert tuple(case.judge_calls for case in fragile.cases) == (0, 0)
    assert fragile.cases[1].judge_cost_usd == 0.0


def test_recorded_run_shares_the_result_identity() -> None:
    """A run record is identified by the result it records."""

    result, candidate = run_tolerant_benchmark()
    recorder = create_recorder()

    record = recorder.record_run(
        result,
        candidate=candidate,
    )

    assert record.id == result.id
    assert record.benchmark_id == DATASET_ID
    assert record.kind is WorkflowBenchmarkExecutionKind.RUN
    assert recorder.executions.executions() == (record,)


def test_recorded_run_identifies_the_candidate() -> None:
    """A run record names the workflow and the resolved candidate it judged."""

    result, candidate = run_tolerant_benchmark()

    record = create_recorder().record_run(
        result,
        candidate=candidate,
    )

    (recorded,) = record.candidates

    assert recorded.workflow == candidate.metadata
    assert recorded.candidate_signature == candidate.signature
    assert recorded.scorecard is None


def test_recorded_run_keeps_every_case_in_dataset_order() -> None:
    """A run record mirrors every case's identity, comparison, and verdict."""

    result, candidate = run_tolerant_benchmark()

    record = create_recorder().record_run(
        result,
        candidate=candidate,
    )

    assert tuple(
        (
            case.case_id,
            case.comparison,
            case.run_id,
            case.evaluation_id,
            case.passed,
        )
        for case in record.candidates[0].cases
    ) == tuple(
        (
            case.case_id,
            case.comparison,
            case.run.id,
            case.evaluation.id,
            case.evaluation.passed,
        )
        for case in result.cases
    )

    assert record.case_ids == (
        EXACT_CASE_ID,
        SEMANTIC_CASE_ID,
    )


def test_recorded_run_keeps_judge_calls_beside_the_case() -> None:
    """Judge calls and their cost are recorded on the judged case only."""

    result, candidate = run_tolerant_benchmark()

    record = create_recorder().record_run(
        result,
        candidate=candidate,
    )

    exact, semantic = record.candidates[0].cases

    assert (exact.judge_calls, exact.judge_cost_usd) == (0, 0.0)
    assert semantic.comparison is OutcomeComparison.SEMANTIC
    assert semantic.judge_calls == 1
    assert semantic.judge_cost_usd == pytest.approx(JUDGE_COST_USD)
    assert record.judge_cost_usd == pytest.approx(result.judge_cost_usd)


def test_recorded_run_saves_every_run_and_evaluation() -> None:
    """Every case run and its evaluation are saved as durable evidence."""

    result, candidate = run_tolerant_benchmark()
    recorder = create_recorder()

    recorder.record_run(
        result,
        candidate=candidate,
    )

    assert recorder.runs.runs() == tuple(case.run for case in result.cases)

    for case in result.cases:
        (evaluation,) = recorder.evaluations.evaluations_for_run(case.run.id)

        assert evaluation.evaluation == case.evaluation


def test_recorded_run_rejects_runs_of_another_workflow() -> None:
    """A run record cannot attribute runs to a workflow that did not produce them."""

    result, candidate = run_tolerant_benchmark()
    recorder = create_recorder()

    impostor = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=UUID(int=7),
            name="impostor",
            description="Claim another workflow's runs.",
        ),
        steps=candidate.steps,
        result=candidate.result,
    )

    with pytest.raises(
        ValueError,
        match=f"^Benchmark case {EXACT_CASE_ID} was not run by workflow {UUID(int=7)}.$",
    ):
        recorder.record_run(
            result,
            candidate=impostor,
        )

    assert recorder.runs.runs() == ()
    assert recorder.evaluations.evaluations() == ()
    assert recorder.executions.executions() == ()


def test_recorded_run_rejects_a_result_without_cases() -> None:
    """A result that executed nothing is not recorded, and nothing is saved."""

    _result, candidate = run_tolerant_benchmark()
    recorder = create_recorder()
    empty = WorkflowBenchmarkResult(dataset_id=DATASET_ID)

    with pytest.raises(
        ValueError,
        match=f"^Benchmark result {empty.id} has no cases to record.$",
    ):
        recorder.record_run(
            empty,
            candidate=candidate,
        )

    assert recorder.executions.executions() == ()


def test_recorded_comparison_shares_the_ranking_identity() -> None:
    """A comparison record is identified by the ranking it records."""

    comparison, ranking, candidates = run_comparison()
    recorder = create_recorder()

    record = recorder.record_comparison(
        comparison,
        ranking,
        candidates=candidates,
        scoring_policy=POLICY,
    )

    assert record.id == ranking.id
    assert record.benchmark_id == DATASET_ID
    assert record.kind is WorkflowBenchmarkExecutionKind.COMPARE
    assert record.scoring_policy == POLICY
    assert recorder.executions.executions() == (record,)


def test_recorded_comparison_ranks_candidates_in_ranking_order() -> None:
    """The record's ranking agrees with the ranking it records."""

    comparison, ranking, candidates = run_comparison()

    record = create_recorder().record_comparison(
        comparison,
        ranking,
        candidates=candidates,
        scoring_policy=POLICY,
    )

    names_by_signature = {candidate.signature: name for name, candidate in candidates.items()}

    assert tuple(
        names_by_signature[candidate.candidate_signature] for candidate in record.ranked_candidates
    ) == tuple(entry.name for entry in ranking.entries)

    assert tuple(candidate.scorecard for candidate in record.ranked_candidates) == tuple(
        entry.scorecard for entry in ranking.entries
    )


def test_recorded_comparison_keeps_comparison_order_for_candidates() -> None:
    """Candidates are stored in the order they were compared."""

    comparison, ranking, candidates = run_comparison()

    record = create_recorder().record_comparison(
        comparison,
        ranking,
        candidates=candidates,
        scoring_policy=POLICY,
    )

    assert tuple(candidate.candidate_signature for candidate in record.candidates) == (
        candidates["tolerant"].signature,
        candidates["fragile"].signature,
    )


def test_recorded_comparison_keeps_run_failures_and_judge_calls() -> None:
    """Failed runs and judge calls are recorded per candidate case."""

    comparison, ranking, candidates = run_comparison()

    record = create_recorder().record_comparison(
        comparison,
        ranking,
        candidates=candidates,
        scoring_policy=POLICY,
    )

    tolerant, fragile = record.candidates

    assert tolerant.run_failures == 0
    assert tolerant.judge_calls == 1
    assert fragile.run_failures == 1
    assert fragile.judge_calls == 0
    assert record.judge_cost_usd == pytest.approx(JUDGE_COST_USD)


def test_recorded_comparison_saves_every_run_and_evaluation() -> None:
    """Every candidate's case runs and evaluations are saved."""

    comparison, ranking, candidates = run_comparison()
    recorder = create_recorder()

    recorder.record_comparison(
        comparison,
        ranking,
        candidates=candidates,
        scoring_policy=POLICY,
    )

    expected_runs = tuple(
        case.run for entry in comparison.candidates for case in entry.result.cases
    )

    assert recorder.runs.runs() == expected_runs
    assert len(recorder.evaluations.evaluations()) == len(expected_runs)


def test_recorded_comparison_rejects_a_ranking_of_other_candidates() -> None:
    """A ranking that does not rank every compared candidate is not recorded."""

    comparison, ranking, candidates = run_comparison()
    recorder = create_recorder()

    partial = WorkflowBenchmarkRanking(
        entries=ranking.entries[:1],
    )

    with pytest.raises(
        ValueError,
        match="^Benchmark ranking must rank every compared candidate exactly once.$",
    ):
        recorder.record_comparison(
            comparison,
            partial,
            candidates=candidates,
            scoring_policy=POLICY,
        )

    assert recorder.runs.runs() == ()
    assert recorder.executions.executions() == ()


def test_recorded_comparison_requires_a_candidate_for_every_name() -> None:
    """Every compared name needs the workflow candidate that ran it."""

    comparison, ranking, candidates = run_comparison()
    recorder = create_recorder()

    with pytest.raises(
        ValueError,
        match="^Benchmark comparison candidate 'fragile' has no workflow candidate.$",
    ):
        recorder.record_comparison(
            comparison,
            ranking,
            candidates={
                "tolerant": candidates["tolerant"],
            },
            scoring_policy=POLICY,
        )

    assert recorder.runs.runs() == ()
    assert recorder.executions.executions() == ()
