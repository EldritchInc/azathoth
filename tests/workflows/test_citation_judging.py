"""Tests that a case's citations are judged from the checks its run kept (ADR 0117)."""

import asyncio
import json
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    CitationExpectation,
    CitedSegment,
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.inputs import InMemoryContentStore
from azathoth.prompting import CITATIONS_RESOURCE_KIND
from azathoth.strategies import StrategyMetadata, StrategyOutcome, StrategyResourceBinding
from azathoth.tools import ToolContentAccess
from azathoth.workflows import (
    CITATIONS_EVIDENCE_LABEL,
    CitationEvidenceError,
    InMemoryRunJournalRepository,
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunner,
    WorkflowValueBinding,
    WorkflowValueReference,
    journaled_extractions,
    journaled_initial_context,
    judge_citations,
    recorded_citation_checks,
    unreadable_citations,
)

STEP_ID = UUID("c16a0000-0000-4000-8000-000000000001")

WORKFLOW_ID = UUID("c16a0000-0000-4000-8000-000000000002")


def check(
    segment: str,
    status: str = "verified",
    source: str = "claim",
) -> dict[str, JsonValue]:
    """Return one kept check of a citation."""

    return {"source": source, "segment": segment, "quote": "q", "status": status}


def required(
    *segments: str,
    on_unverified: str = "fail",
) -> CitationExpectation:
    """Return an expectation requiring some segments of the claim."""

    return CitationExpectation.model_validate(
        {
            "require": [{"source": "claim", "segment": segment} for segment in segments],
            "on_unverified": on_unverified,
        }
    )


def outcome(
    score: float = 1.0,
    threshold: float = 1.0,
) -> EvaluationResult:
    """Return an outcome's evaluation."""

    return EvaluationResult(
        evaluator_name="exact",
        score=score,
        threshold=threshold,
        status=EvaluationStatus.PASSED if score >= threshold else EvaluationStatus.FAILED,
        reason="The result matched.",
        evidence=(EvaluationEvidence(label="expected", value=1),),
    )


class CitingStrategy:
    """A strategy that keeps records of checks, as a cited step does (ADR 0116)."""

    def __init__(
        self,
        store: InMemoryContentStore,
        records: list[list[dict[str, JsonValue]]],
        others: tuple[StrategyResourceBinding, ...] = (),
    ) -> None:
        self._store = store
        self._records = records
        self._others = others

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return StrategyMetadata(
            id=STEP_ID, name="cite", description="Keep checks.", version="1.0.0"
        )

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Keep each record; output every check."""

        resources = tuple(
            StrategyResourceBinding(
                kind=CITATIONS_RESOURCE_KIND,
                identifier=self._store.put(
                    json.dumps({"checks": record}, sort_keys=True).encode("utf-8")
                ),
            )
            for record in self._records
        )

        return StrategyOutcome(
            output={
                "received": "December 14",
                "citations": [check for record in self._records for check in record],
            },
            resources=(*self._others, *resources),
        )


def candidate(
    strategy: CitingStrategy,
) -> WorkflowCandidate:
    """Return a one-step workflow whose result is its step's output."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID, name="cite", description="Cite.", version="1.0.0"
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=strategy,
                outputs=(WorkflowValueBinding(name="answer"),),
            ),
        ),
        result=WorkflowValueReference(producer_step_id=STEP_ID, name="answer"),
    )


def runner(
    store: InMemoryContentStore | None,
) -> WorkflowRunner:
    """Return a runner given a store's content, or none."""

    if store is None:
        return WorkflowRunner()

    journal = InMemoryRunJournalRepository()

    return WorkflowRunner(
        journal=journal,
        content=ToolContentAccess(
            store=store,
            initial_context=lambda run_id: journaled_initial_context(journal, run_id),
            kept_extractions=lambda run_id: journaled_extractions(journal, run_id),
        ),
    )


def kept_run(
    records: list[list[dict[str, JsonValue]]],
) -> tuple[WorkflowRun, InMemoryContentStore]:
    """Run a step keeping some records; return the run and the store holding them."""

    store = InMemoryContentStore()
    run = asyncio.run(
        runner(store).run_recording_failures(candidate(CitingStrategy(store, records)), Context())
    )

    return run, store


def test_a_runs_checks_are_read_from_its_records_in_order() -> None:
    run, store = kept_run([[check("p1.s1")], [check("p1.s2", "quote_not_found")]])

    assert recorded_citation_checks(run, store) == (
        check("p1.s1"),
        check("p1.s2", "quote_not_found"),
    )


def test_only_a_runs_citation_records_are_read() -> None:
    store = InMemoryContentStore()
    other = StrategyResourceBinding(kind="model", identifier="test/citing")
    run = asyncio.run(
        runner(store).run_recording_failures(
            candidate(CitingStrategy(store, [[check("p1.s1")]], others=(other,))), Context()
        )
    )

    assert recorded_citation_checks(run, store) == (check("p1.s1"),)


def test_a_run_that_kept_no_records_has_no_checks_with_or_without_a_store() -> None:
    run, _ = kept_run([])

    assert recorded_citation_checks(run, None) == ()


def test_records_without_a_store_cannot_be_read() -> None:
    run, _ = kept_run([[check("p1.s1")]])

    with pytest.raises(CitationEvidenceError) as raised:
        recorded_citation_checks(run, None)

    assert str(raised.value) == (
        f"Run {run.id} kept citation records, which cannot be read: it has no content store."
    )


def record_of(
    run: WorkflowRun,
) -> str:
    """Return the digest of the one record a run's step kept."""

    execution = run.steps[0].execution

    assert execution is not None

    (record,) = execution.resources

    return record.identifier


class FixedStore(InMemoryContentStore):
    """A content store holding fixed content under one digest, whatever it hashes to."""

    def __init__(
        self,
        digest: str,
        content: bytes,
    ) -> None:
        super().__init__()
        self._digest = digest
        self._fixed = content

    def get(
        self,
        digest: str,
    ) -> bytes | None:
        """Return the fixed content under its digest, and nothing else."""

        return self._fixed if digest == self._digest else None


def test_a_record_the_store_no_longer_holds_cannot_be_read() -> None:
    run, _ = kept_run([[check("p1.s1")]])

    with pytest.raises(CitationEvidenceError) as raised:
        recorded_citation_checks(run, InMemoryContentStore())

    assert str(raised.value) == (
        f"Run {run.id} kept citation record {record_of(run)}, which the content store "
        "no longer holds."
    )


def test_a_record_that_holds_no_checks_cannot_be_read() -> None:
    run, _ = kept_run([[check("p1.s1")]])

    with pytest.raises(CitationEvidenceError) as raised:
        recorded_citation_checks(run, FixedStore(record_of(run), b"{}"))

    assert str(raised.value) == f"Content {record_of(run)} is not a record of citation checks."


def test_a_case_whose_required_citations_verified_passes_as_its_outcome_did() -> None:
    judged = judge_citations(outcome(), required("p1.s2"), [check("p1.s2"), check("p1.s1")])

    assert (judged.status, judged.score, judged.threshold) == (EvaluationStatus.PASSED, 1.0, 1.0)
    assert judged.reason == (
        "The result matched. Citations: 1 of 1 required citations verified; 2 of 2 "
        "citations verified."
    )
    assert judged.evidence[0] == EvaluationEvidence(label="expected", value=1)
    assert judged.evidence[1] == EvaluationEvidence(
        label=CITATIONS_EVIDENCE_LABEL,
        value={
            "required": 1,
            "missing": [],
            "checks": 2,
            "verified": 2,
            "unverified": 0,
            "on_unverified": "fail",
        },
    )


def test_a_required_citation_no_check_verified_fails_the_case() -> None:
    judged = judge_citations(
        outcome(),
        required("p1.s2", "p2.s1", on_unverified="ignore"),
        [check("p1.s2"), check("p2.s1", "quote_not_found"), check("p2.s1", source="other")],
    )

    assert (judged.status, judged.score) == (EvaluationStatus.FAILED, 0.5)
    assert judged.reason == (
        "The result matched. Citations: 1 of 2 required citations verified; 2 of 3 "
        "citations verified. Missing: segment p2.s1 of 'claim'."
    )
    assert judged.evidence[1].value == {
        "required": 2,
        "missing": [{"source": "claim", "segment": "p2.s1"}],
        "checks": 3,
        "verified": 2,
        "unverified": 1,
        "on_unverified": "ignore",
    }


@pytest.mark.parametrize("status", ["verified", "verified_normalized"])
def test_a_check_verified_either_way_meets_a_requirement(
    status: str,
) -> None:
    assert judge_citations(outcome(), required("p1.s2"), [check("p1.s2", status)]).passed


def test_an_unverified_citation_fails_the_case_unless_it_is_ignored() -> None:
    checks = [check("p1.s2"), check("p1.s1", "unknown_segment"), check("p2.s1"), check("x")]

    failed = judge_citations(outcome(), required("p1.s2"), checks)
    ignored = judge_citations(outcome(), required("p1.s2", on_unverified="ignore"), checks)

    assert (failed.status, failed.score) == (EvaluationStatus.FAILED, 0.75)
    assert (ignored.status, ignored.score) == (EvaluationStatus.PASSED, 1.0)


def test_a_case_requiring_nothing_fails_only_on_unverified_citations() -> None:
    assert judge_citations(outcome(), required(), [check("p1.s2")]).passed
    assert judge_citations(outcome(), required(), []).passed
    assert not judge_citations(outcome(), required(), [check("p1.s2", "quote_not_found")]).passed


def test_a_case_whose_outcome_failed_still_fails_scored_by_both() -> None:
    judged = judge_citations(outcome(0.4, 0.5), required("p1.s2", "p2.s1"), [check("p1.s2")])

    assert (judged.status, judged.score, judged.threshold) == (
        EvaluationStatus.FAILED,
        0.2,
        0.5,
    )


def test_a_case_whose_outcome_failed_fails_however_well_it_cited() -> None:
    judged = judge_citations(outcome(0.4, 0.5), required("p1.s2"), [check("p1.s2")])

    assert (judged.status, judged.score, judged.threshold) == (
        EvaluationStatus.FAILED,
        0.4,
        0.5,
    )


def test_a_case_its_citations_bring_below_its_threshold_keeps_that_score() -> None:
    judged = judge_citations(outcome(0.9, 0.7), required("p1.s2", "p2.s1"), [check("p1.s2")])

    assert (judged.status, judged.threshold) == (EvaluationStatus.FAILED, 0.7)
    assert judged.score == pytest.approx(0.45)


def test_a_case_its_citations_fail_scores_below_its_threshold() -> None:
    judged = judge_citations(
        outcome(1.0, 0.7),
        required("p1.s2", "p2.s1", "p3.s1", "p4.s1"),
        [check("p1.s2"), check("p2.s1"), check("p3.s1")],
    )

    assert (judged.status, judged.threshold) == (EvaluationStatus.FAILED, 0.7)
    assert judged.score == pytest.approx(0.7 * 0.75)


def test_a_threshold_every_score_meets_becomes_one_when_citations_fail() -> None:
    judged = judge_citations(outcome(0.0, 0.0), required("p1.s2"), [])

    assert (judged.status, judged.score, judged.threshold) == (EvaluationStatus.FAILED, 0.0, 1.0)


def test_unreadable_citations_fail_the_case_naming_why() -> None:
    judged = unreadable_citations(outcome(), "it has no content store.")

    assert (judged.status, judged.score, judged.threshold) == (EvaluationStatus.FAILED, 0.0, 1.0)
    assert (
        judged.reason == "The result matched. Citations cannot be judged: it has no content store."
    )
    assert judged.evidence == outcome().evidence
    assert unreadable_citations(outcome(0.0, 0.0), "x").threshold == 1.0


def benchmark(
    citations: CitationExpectation | None,
    value: JsonValue = None,
) -> BenchmarkDataset:
    """Return a one-case benchmark expecting the answer, citing some segments."""

    expected: dict[str, Any] = {
        "description": "Received.",
        "value": value
        if value is not None
        else {"received": "December 14", "citations": [{"source": "claim", "segment": "p1.s2"}]},
        "comparison": OutcomeComparison.EXACT,
    }

    if citations is not None:
        expected["citations"] = citations

    return BenchmarkDataset(
        name="claims",
        description="Claims.",
        cases=(BenchmarkCase(input=None, expected=ExpectedOutcome.model_validate(expected)),),
    )


def benchmarked(
    citations: CitationExpectation | None,
    *,
    records: list[list[dict[str, JsonValue]]],
    give_store: bool = True,
) -> EvaluationResult:
    """Run the one-case benchmark; return its case's evaluation."""

    store = InMemoryContentStore()
    result = asyncio.run(
        WorkflowBenchmarkRunner(runner=runner(store if give_store else None)).run(
            benchmark(citations),
            lambda _case: candidate(CitingStrategy(store, records)),
        )
    )

    return result.cases[0].evaluation


def test_a_benchmark_judges_a_cited_case_on_its_runs_records() -> None:
    passed = benchmarked(required("p1.s2"), records=[[check("p1.s2")]])
    failed = benchmarked(required("p2.s1"), records=[[check("p1.s2")]])

    assert passed.passed
    assert passed.evidence[-1].label == CITATIONS_EVIDENCE_LABEL
    assert not failed.passed
    assert "Missing: segment p2.s1 of 'claim'." in failed.reason


def test_a_benchmark_judges_a_case_naming_no_citations_on_its_outcome_alone() -> None:
    evaluation = benchmarked(None, records=[[check("p1.s2", "quote_not_found")]])

    assert evaluation.passed
    assert all(item.label != CITATIONS_EVIDENCE_LABEL for item in evaluation.evidence)


def test_a_benchmark_without_a_store_fails_a_cited_case_naming_why() -> None:
    evaluation = benchmarked(required("p1.s2"), records=[[check("p1.s2")]], give_store=False)

    assert not evaluation.passed
    assert evaluation.reason.endswith(
        "kept citation records, which cannot be read: it has no content store."
    )


def test_a_required_segment_is_a_cited_segment() -> None:
    assert required("p1.s2").require == (CitedSegment(source="claim", segment="p1.s2"),)
