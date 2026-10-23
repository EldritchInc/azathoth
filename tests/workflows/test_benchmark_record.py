"""Tests for durable workflow benchmark execution records."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.evaluation import OutcomeComparison
from azathoth.workflows import (
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionCase,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkExecutionRecord,
    WorkflowCandidateSignature,
    WorkflowMetadata,
    WorkflowScorecard,
    WorkflowScoringPolicy,
)

EXECUTION_ID = UUID("e0e0e0e0-e0e0-e0e0-e0e0-e0e0e0e0e0e0")

BENCHMARK_ID = UUID("12121212-1212-1212-1212-121212121212")

FIRST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")
SECOND_STRATEGY_ID = UUID("99999999-9999-9999-9999-999999999999")

FIRST_CANDIDATE_ID = UUID("abababab-abab-abab-abab-abababababab")
SECOND_CANDIDATE_ID = UUID("cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")

FIRST_CASE_ID = UUID("c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1")
SECOND_CASE_ID = UUID("c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2")
THIRD_CASE_ID = UUID("c3c3c3c3-c3c3-c3c3-c3c3-c3c3c3c3c3c3")

CASE_IDS = (
    FIRST_CASE_ID,
    SECOND_CASE_ID,
    THIRD_CASE_ID,
)

POLICY = WorkflowScoringPolicy(
    target_latency_seconds=2.0,
    target_cost_usd=0.01,
)

RECORDED_AT = datetime(
    2026,
    10,
    23,
    9,
    0,
    tzinfo=UTC,
)


def run_id(
    candidate: int,
    case: int,
) -> UUID:
    """Return a deterministic run identifier for one candidate and case."""

    return UUID(f"{candidate:08x}-0000-4000-8000-{case:012x}")


def evaluation_id(
    candidate: int,
    case: int,
) -> UUID:
    """Return a deterministic evaluation identifier for one candidate and case."""

    return UUID(f"{candidate:08x}-0000-4000-9000-{case:012x}")


def create_scorecard(
    overall_score: float,
) -> WorkflowScorecard:
    """Create deterministic workflow scoring evidence."""

    return WorkflowScorecard(
        quality_score=overall_score,
        reliability_score=overall_score,
        latency_score=overall_score,
        cost_score=overall_score,
        overall_score=overall_score,
        rationale="Deterministic test score.",
    )


def create_cases(
    candidate: int,
    *,
    passed: tuple[bool, bool, bool],
    case_ids: tuple[UUID, ...] = CASE_IDS,
) -> tuple[WorkflowBenchmarkExecutionCase, ...]:
    """Create exact, semantic, and failed-run cases for one candidate.

    The second case is judged semantically by two judge calls costing
    $0.002 in total. The third case is a run failure.
    """

    comparisons = (
        OutcomeComparison.EXACT,
        OutcomeComparison.SEMANTIC,
        OutcomeComparison.EXACT,
    )

    return tuple(
        WorkflowBenchmarkExecutionCase(
            case_id=case_id,
            comparison=comparisons[index],
            run_id=run_id(candidate, index),
            evaluation_id=evaluation_id(candidate, index),
            passed=passed[index],
            run_failure=index == 2,
            judge_calls=2 if index == 1 else 0,
            judge_cost_usd=0.002 if index == 1 else 0.0,
        )
        for index, case_id in enumerate(case_ids)
    )


def create_candidate(
    *,
    candidate_id: UUID = FIRST_CANDIDATE_ID,
    workflow_id: UUID = FIRST_WORKFLOW_ID,
    strategy_id: UUID = FIRST_STRATEGY_ID,
    cases: tuple[WorkflowBenchmarkExecutionCase, ...] | None = None,
    score: float | None = None,
) -> WorkflowBenchmarkExecutionCandidate:
    """Create one deterministic benchmark execution candidate."""

    return WorkflowBenchmarkExecutionCandidate(
        id=candidate_id,
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow {workflow_id}",
            description="Execute a benchmarked workflow.",
            version="1.0.0",
        ),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=workflow_id,
            strategy_ids=(strategy_id,),
        ),
        cases=(
            cases
            if cases is not None
            else create_cases(
                1,
                passed=(True, True, False),
            )
        ),
        scorecard=create_scorecard(score) if score is not None else None,
    )


def create_second_candidate(
    *,
    cases: tuple[WorkflowBenchmarkExecutionCase, ...] | None = None,
    score: float | None = 0.4,
) -> WorkflowBenchmarkExecutionCandidate:
    """Create the second, weaker compared candidate."""

    return create_candidate(
        candidate_id=SECOND_CANDIDATE_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        strategy_id=SECOND_STRATEGY_ID,
        cases=(
            cases
            if cases is not None
            else create_cases(
                2,
                passed=(False, True, False),
            )
        ),
        score=score,
    )


def create_run_record() -> WorkflowBenchmarkExecutionRecord:
    """Create a valid execution record for one benchmark run."""

    return WorkflowBenchmarkExecutionRecord(
        id=EXECUTION_ID,
        benchmark_id=BENCHMARK_ID,
        kind=WorkflowBenchmarkExecutionKind.RUN,
        candidates=(create_candidate(),),
        recorded_at=RECORDED_AT,
    )


def create_compare_record(
    *,
    candidates: tuple[WorkflowBenchmarkExecutionCandidate, ...] | None = None,
    ranking: tuple[UUID, ...] = (
        SECOND_CANDIDATE_ID,
        FIRST_CANDIDATE_ID,
    ),
    scoring_policy: WorkflowScoringPolicy | None = POLICY,
) -> WorkflowBenchmarkExecutionRecord:
    """Create an execution record comparing two benchmark candidates.

    The default ranking deliberately lists the second candidate first, so
    tests prove rank order comes from the ranking, not candidate order.
    """

    return WorkflowBenchmarkExecutionRecord(
        id=EXECUTION_ID,
        benchmark_id=BENCHMARK_ID,
        kind=WorkflowBenchmarkExecutionKind.COMPARE,
        candidates=(
            candidates
            if candidates is not None
            else (
                create_candidate(score=0.8),
                create_second_candidate(),
            )
        ),
        ranking=ranking,
        scoring_policy=scoring_policy,
        recorded_at=RECORDED_AT,
    )


def test_execution_kinds_use_the_benchmark_command_names() -> None:
    """Execution kinds are stored as the commands that produced them."""

    assert tuple(kind.value for kind in WorkflowBenchmarkExecutionKind) == (
        "run",
        "compare",
    )


def test_candidate_reports_pass_counts_and_accuracy() -> None:
    """Candidates count passing cases across every comparison."""

    candidate = create_candidate()

    assert candidate.case_ids == CASE_IDS
    assert candidate.cases_run == 3
    assert candidate.cases_passed == 2
    assert candidate.accuracy == pytest.approx(2 / 3)


def test_candidate_reports_run_failures() -> None:
    """Candidates count the cases judged as failed runs."""

    assert create_candidate().run_failures == 1


def test_candidate_reports_comparison_tallies_in_declaration_order() -> None:
    """Tallies follow comparison declaration order and omit unused comparisons."""

    tallies = create_candidate().comparison_tallies

    assert tuple(
        (
            tally.comparison,
            tally.cases_run,
            tally.cases_passed,
        )
        for tally in tallies
    ) == (
        (OutcomeComparison.EXACT, 2, 1),
        (OutcomeComparison.SEMANTIC, 1, 1),
    )


def test_candidate_reports_judge_totals() -> None:
    """Candidates total the judge calls recorded beside their cases."""

    candidate = create_candidate()

    assert candidate.judged_semantically is True
    assert candidate.judge_calls == 2
    assert candidate.judge_cost_usd == pytest.approx(0.002)


def test_candidate_without_semantic_cases_was_not_judged_semantically() -> None:
    """A candidate with only deterministic cases made no judge calls."""

    candidate = create_candidate(
        cases=(
            WorkflowBenchmarkExecutionCase(
                case_id=FIRST_CASE_ID,
                comparison=OutcomeComparison.SCHEMA,
                run_id=run_id(1, 0),
                evaluation_id=evaluation_id(1, 0),
                passed=True,
            ),
        ),
    )

    assert candidate.judged_semantically is False
    assert candidate.judge_calls == 0
    assert candidate.judge_cost_usd == 0.0
    assert candidate.run_failures == 0


def test_candidate_finds_cases_by_case_and_run() -> None:
    """Candidates resolve their cases by case and run identity."""

    candidate = create_candidate()

    second_case = candidate.case(SECOND_CASE_ID)
    run_case = candidate.case_for_run(run_id(1, 2))

    assert second_case is not None
    assert second_case.run_id == run_id(1, 1)
    assert run_case is not None
    assert run_case.case_id == THIRD_CASE_ID
    assert candidate.case(UUID(int=0)) is None
    assert candidate.case_for_run(UUID(int=0)) is None


def test_candidate_requires_signature_for_executed_workflow() -> None:
    """Candidate signatures must reference the executed workflow."""

    with pytest.raises(
        ValidationError,
        match="Benchmark execution candidate signature must reference the executed workflow.",
    ):
        WorkflowBenchmarkExecutionCandidate(
            workflow=WorkflowMetadata(
                id=FIRST_WORKFLOW_ID,
                name="first workflow",
                description="Execute the first workflow.",
            ),
            candidate_signature=WorkflowCandidateSignature(
                workflow_id=SECOND_WORKFLOW_ID,
                strategy_ids=(FIRST_STRATEGY_ID,),
            ),
            cases=create_cases(
                1,
                passed=(True, True, True),
            ),
        )


def test_candidate_requires_at_least_one_case() -> None:
    """A candidate that executed no case is not evidence."""

    with pytest.raises(ValidationError):
        create_candidate(
            cases=(),
        )


def test_candidate_rejects_duplicate_case_ids() -> None:
    """A candidate executes each benchmark case at most once."""

    with pytest.raises(
        ValidationError,
        match="Benchmark execution candidate cases must use unique case identifiers.",
    ):
        create_candidate(
            cases=create_cases(
                1,
                passed=(True, True, True),
                case_ids=(
                    FIRST_CASE_ID,
                    FIRST_CASE_ID,
                    THIRD_CASE_ID,
                ),
            ),
        )


def test_case_rejects_negative_judge_totals() -> None:
    """Judge calls and judge cost cannot be negative."""

    with pytest.raises(ValidationError):
        WorkflowBenchmarkExecutionCase(
            case_id=FIRST_CASE_ID,
            comparison=OutcomeComparison.SEMANTIC,
            run_id=run_id(1, 0),
            evaluation_id=evaluation_id(1, 0),
            passed=True,
            judge_calls=-1,
        )

    with pytest.raises(ValidationError):
        WorkflowBenchmarkExecutionCase(
            case_id=FIRST_CASE_ID,
            comparison=OutcomeComparison.SEMANTIC,
            run_id=run_id(1, 0),
            evaluation_id=evaluation_id(1, 0),
            passed=True,
            judge_cost_usd=-0.01,
        )


def test_case_defaults_to_no_run_failure_and_no_judging() -> None:
    """Cases record no run failure and no judge calls unless stated."""

    case = WorkflowBenchmarkExecutionCase(
        case_id=FIRST_CASE_ID,
        comparison=OutcomeComparison.EXACT,
        run_id=run_id(1, 0),
        evaluation_id=evaluation_id(1, 0),
        passed=False,
    )

    assert case.run_failure is False
    assert case.judge_calls == 0
    assert case.judge_cost_usd == 0.0


def test_run_record_is_unranked() -> None:
    """A run record has one candidate, no ranking, and no winner."""

    record = create_run_record()

    assert record.kind is WorkflowBenchmarkExecutionKind.RUN
    assert record.ranking == ()
    assert record.scoring_policy is None
    assert record.winner is None
    assert record.ranked_candidates == record.candidates
    assert record.case_ids == CASE_IDS


def test_run_record_reports_judge_totals() -> None:
    """A run record totals the judge calls of its one candidate."""

    record = create_run_record()

    assert record.judge_calls == 2
    assert record.judge_cost_usd == pytest.approx(0.002)


def test_run_record_rejects_more_than_one_candidate() -> None:
    """A run executes exactly one workflow."""

    with pytest.raises(
        ValidationError,
        match="Benchmark run executions must record exactly one candidate.",
    ):
        WorkflowBenchmarkExecutionRecord(
            benchmark_id=BENCHMARK_ID,
            kind=WorkflowBenchmarkExecutionKind.RUN,
            candidates=(
                create_candidate(),
                create_second_candidate(score=None),
            ),
        )


def test_run_record_rejects_a_ranking() -> None:
    """A run ranks nothing."""

    with pytest.raises(
        ValidationError,
        match="Benchmark run executions cannot record a ranking.",
    ):
        WorkflowBenchmarkExecutionRecord(
            benchmark_id=BENCHMARK_ID,
            kind=WorkflowBenchmarkExecutionKind.RUN,
            candidates=(create_candidate(),),
            ranking=(FIRST_CANDIDATE_ID,),
        )


def test_run_record_rejects_a_scoring_policy() -> None:
    """A run scores nothing, so it has no scoring policy."""

    with pytest.raises(
        ValidationError,
        match="Benchmark run executions cannot record a scoring policy.",
    ):
        WorkflowBenchmarkExecutionRecord(
            benchmark_id=BENCHMARK_ID,
            kind=WorkflowBenchmarkExecutionKind.RUN,
            candidates=(create_candidate(),),
            scoring_policy=POLICY,
        )


def test_run_record_rejects_a_scorecard() -> None:
    """A run's candidate is not scored."""

    with pytest.raises(
        ValidationError,
        match="Benchmark run executions cannot record a scorecard.",
    ):
        WorkflowBenchmarkExecutionRecord(
            benchmark_id=BENCHMARK_ID,
            kind=WorkflowBenchmarkExecutionKind.RUN,
            candidates=(create_candidate(score=0.5),),
        )


def test_record_requires_at_least_one_candidate() -> None:
    """An execution that judged no candidate is not evidence."""

    with pytest.raises(ValidationError):
        WorkflowBenchmarkExecutionRecord(
            benchmark_id=BENCHMARK_ID,
            kind=WorkflowBenchmarkExecutionKind.RUN,
            candidates=(),
        )


def test_compare_record_orders_candidates_by_ranking() -> None:
    """Rank order comes from the ranking, not from candidate order."""

    record = create_compare_record()

    assert tuple(candidate.id for candidate in record.ranked_candidates) == (
        SECOND_CANDIDATE_ID,
        FIRST_CANDIDATE_ID,
    )

    winner = record.winner

    assert winner is not None
    assert winner.id == SECOND_CANDIDATE_ID
    assert record.scoring_policy == POLICY


def test_compare_record_reports_judge_totals_across_candidates() -> None:
    """A comparison totals the judge calls of every candidate."""

    record = create_compare_record()

    assert record.judge_calls == 4
    assert record.judge_cost_usd == pytest.approx(0.004)


def test_compare_record_finds_candidates_by_id_and_run() -> None:
    """Comparisons resolve candidates by identity and by any of their runs."""

    record = create_compare_record()

    candidate = record.candidate(FIRST_CANDIDATE_ID)
    run_candidate = record.candidate_for_run(run_id(2, 1))

    assert candidate is not None
    assert candidate.workflow.id == FIRST_WORKFLOW_ID
    assert run_candidate is not None
    assert run_candidate.id == SECOND_CANDIDATE_ID
    assert record.candidate(UUID(int=0)) is None
    assert record.candidate_for_run(UUID(int=0)) is None


def test_compare_record_requires_at_least_two_candidates() -> None:
    """A comparison compares at least two workflows."""

    with pytest.raises(
        ValidationError,
        match="Benchmark compare executions must record at least two candidates.",
    ):
        create_compare_record(
            candidates=(create_candidate(score=0.8),),
            ranking=(FIRST_CANDIDATE_ID,),
        )


def test_compare_record_requires_a_scoring_policy() -> None:
    """A saved ranking must be explainable by the targets that produced it."""

    with pytest.raises(
        ValidationError,
        match="Benchmark compare executions must record their scoring policy.",
    ):
        create_compare_record(
            scoring_policy=None,
        )


def test_compare_record_requires_every_scorecard() -> None:
    """Every compared candidate is scored."""

    with pytest.raises(
        ValidationError,
        match="Benchmark compare executions must record every candidate scorecard.",
    ):
        create_compare_record(
            candidates=(
                create_candidate(score=0.8),
                create_second_candidate(score=None),
            ),
        )


def test_compare_record_requires_identical_cases() -> None:
    """Compared candidates are judged on the same benchmark cases."""

    with pytest.raises(
        ValidationError,
        match="Benchmark compare execution candidates must be judged on the same cases.",
    ):
        create_compare_record(
            candidates=(
                create_candidate(score=0.8),
                create_second_candidate(
                    cases=create_cases(
                        2,
                        passed=(True, True, True),
                        case_ids=(
                            FIRST_CASE_ID,
                            SECOND_CASE_ID,
                        ),
                    ),
                ),
            ),
        )


def test_compare_record_requires_cases_in_the_same_order() -> None:
    """Compared candidates record cases in the same dataset order."""

    with pytest.raises(
        ValidationError,
        match="Benchmark compare execution candidates must be judged on the same cases.",
    ):
        create_compare_record(
            candidates=(
                create_candidate(score=0.8),
                create_second_candidate(
                    cases=create_cases(
                        2,
                        passed=(True, True, True),
                        case_ids=(
                            THIRD_CASE_ID,
                            SECOND_CASE_ID,
                            FIRST_CASE_ID,
                        ),
                    ),
                ),
            ),
        )


def test_compare_record_rejects_duplicate_ranking_entries() -> None:
    """A ranking lists each candidate once."""

    with pytest.raises(
        ValidationError,
        match="Benchmark execution ranking cannot contain duplicate candidate identifiers.",
    ):
        create_compare_record(
            ranking=(
                FIRST_CANDIDATE_ID,
                FIRST_CANDIDATE_ID,
            ),
        )


def test_compare_record_rejects_an_incomplete_ranking() -> None:
    """A ranking covers every candidate."""

    with pytest.raises(
        ValidationError,
        match="Benchmark execution ranking must reference every candidate exactly once.",
    ):
        create_compare_record(
            ranking=(FIRST_CANDIDATE_ID,),
        )


def test_compare_record_rejects_an_unknown_ranking_entry() -> None:
    """A ranking references only recorded candidates."""

    with pytest.raises(
        ValidationError,
        match="Benchmark execution ranking must reference every candidate exactly once.",
    ):
        create_compare_record(
            ranking=(
                FIRST_CANDIDATE_ID,
                UUID(int=0),
            ),
        )


def test_record_rejects_duplicate_candidate_ids() -> None:
    """Every candidate has a distinct identity."""

    with pytest.raises(
        ValidationError,
        match="Benchmark execution candidates must use unique candidate identifiers.",
    ):
        create_compare_record(
            candidates=(
                create_candidate(score=0.8),
                create_candidate(
                    workflow_id=SECOND_WORKFLOW_ID,
                    cases=create_cases(
                        2,
                        passed=(True, True, True),
                    ),
                    score=0.4,
                ),
            ),
            ranking=(FIRST_CANDIDATE_ID,),
        )


def test_record_rejects_duplicate_run_ids_across_candidates() -> None:
    """Every case across all candidates is a distinct run."""

    first_cases = create_cases(
        1,
        passed=(True, True, True),
    )

    second_cases = tuple(
        case.model_copy(
            update={
                "evaluation_id": evaluation_id(2, index),
            },
        )
        for index, case in enumerate(first_cases)
    )

    with pytest.raises(
        ValidationError,
        match="Benchmark execution cases must use unique run identifiers.",
    ):
        create_compare_record(
            candidates=(
                create_candidate(
                    cases=first_cases,
                    score=0.8,
                ),
                create_second_candidate(
                    cases=second_cases,
                ),
            ),
        )


def test_record_rejects_duplicate_evaluation_ids_across_candidates() -> None:
    """Every case across all candidates references a distinct evaluation."""

    first_cases = create_cases(
        1,
        passed=(True, True, True),
    )

    second_cases = tuple(
        case.model_copy(
            update={
                "run_id": run_id(2, index),
            },
        )
        for index, case in enumerate(first_cases)
    )

    with pytest.raises(
        ValidationError,
        match="Benchmark execution cases must use unique evaluation identifiers.",
    ):
        create_compare_record(
            candidates=(
                create_candidate(
                    cases=first_cases,
                    score=0.8,
                ),
                create_second_candidate(
                    cases=second_cases,
                ),
            ),
        )


def test_record_defaults_identity_and_time() -> None:
    """Records receive a fresh identity and a UTC recording time."""

    first = WorkflowBenchmarkExecutionRecord(
        benchmark_id=BENCHMARK_ID,
        kind=WorkflowBenchmarkExecutionKind.RUN,
        candidates=(create_candidate(),),
    )

    second = WorkflowBenchmarkExecutionRecord(
        benchmark_id=BENCHMARK_ID,
        kind=WorkflowBenchmarkExecutionKind.RUN,
        candidates=(create_candidate(),),
    )

    assert first.id != second.id
    assert first.recorded_at.tzinfo is not None
    assert first.recorded_at.utcoffset() == UTC.utcoffset(None)


def test_run_record_round_trips_through_json() -> None:
    """Run records survive durable JSON encoding unchanged."""

    record = create_run_record()

    decoded = WorkflowBenchmarkExecutionRecord.model_validate_json(
        record.model_dump_json(),
    )

    assert decoded == record


def test_compare_record_round_trips_through_json() -> None:
    """Comparison records keep their ranking and policy through JSON."""

    record = create_compare_record()

    decoded = WorkflowBenchmarkExecutionRecord.model_validate_json(
        record.model_dump_json(),
    )

    assert decoded == record
    assert decoded.ranking == record.ranking
    assert decoded.scoring_policy == POLICY
