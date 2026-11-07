"""Judging what a benchmark case's run cited, from the checks it kept (ADR 0117).

A case may name the segments its run must cite. Whether it did is read from
the engine's records, never from the result: every check a cited step of
the run kept is in the content store, named by the step's `citations`
resource (ADR 0116), so a result cannot claim a citation verified that no
check verified.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import JsonValue

from azathoth.citations import VERIFIED_STATUSES
from azathoth.evaluation import (
    CitationExpectation,
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.inputs import ContentStore
from azathoth.prompting import (
    CITATIONS_RESOURCE_KIND,
    CitationCheckError,
    stored_citation_checks,
)
from azathoth.workflows.execution import WorkflowRun

CITATIONS_EVIDENCE_LABEL: Final = "citations"
"""The label of the evidence a case's citation expectation was judged on."""

_VERIFIED: Final = frozenset(status.value for status in VERIFIED_STATUSES)


class CitationEvidenceError(ValueError):
    """Raised when the checks a run kept cannot be read."""


def recorded_citation_checks(
    run: WorkflowRun,
    store: ContentStore | None,
) -> tuple[Mapping[str, JsonValue], ...]:
    """Return every check the cited steps of one run kept, in step order.

    Raises:
        CitationEvidenceError: The run kept a record and there is no content
            store to read it from, the store no longer holds it, or what it
            holds is not a record of checks.
    """

    records = tuple(
        resource.identifier
        for step in run.steps
        if step.execution is not None
        for resource in step.execution.resources
        if resource.kind == CITATIONS_RESOURCE_KIND
    )

    if records and store is None:
        raise CitationEvidenceError(
            f"Run {run.id} kept citation records, which cannot be read: it has no content store."
        )

    checks: list[Mapping[str, JsonValue]] = []

    for digest in records:
        assert store is not None

        try:
            kept = stored_citation_checks(store, digest)
        except CitationCheckError as exc:
            raise CitationEvidenceError(str(exc)) from exc

        if kept is None:
            raise CitationEvidenceError(
                f"Run {run.id} kept citation record {digest}, which the content store no "
                "longer holds."
            )

        checks.extend(kept)

    return tuple(checks)


def judge_citations(
    outcome: EvaluationResult,
    expectation: CitationExpectation,
    checks: Sequence[Mapping[str, JsonValue]],
) -> EvaluationResult:
    """Return a case's evaluation once its citation expectation is judged too.

    The case passes only if its outcome passed, every required segment was
    met by a verified check, and, under `on_unverified` `fail`, every check
    verified. Its score is the outcome's, times the fraction of required
    segments met and, under `fail`, the fraction of checks that verified. A
    case its citations fail scores below its threshold, which is the
    outcome's unless that was 0, which every score meets; it is then 1.
    """

    verified = [check for check in checks if check.get("status") in _VERIFIED]
    unverified = len(checks) - len(verified)
    cited = {(check.get("source"), check.get("segment")) for check in verified}
    missing = [
        required
        for required in expectation.require
        if (required.source, required.segment) not in cited
    ]
    counted = unverified if expectation.on_unverified == "fail" else 0
    met = len(expectation.require) - len(missing)
    fraction = (met / len(expectation.require) if expectation.require else 1.0) * (
        len(verified) / len(checks) if counted else 1.0
    )
    passed = outcome.passed and not missing and not counted
    score, threshold = (
        (outcome.score * fraction, outcome.threshold)
        if passed or not outcome.passed
        else _failing(outcome.score * fraction, outcome.threshold, fraction)
    )
    reason = (
        f"{outcome.reason} Citations: {met} of {len(expectation.require)} required "
        f"citations verified; {len(verified)} of {len(checks)} citations verified."
    )

    if missing:
        reason += " Missing: " + ", ".join(
            f"segment {required.segment} of {required.source!r}" for required in missing
        )
        reason += "."

    return EvaluationResult(
        id=outcome.id,
        evaluator_name=outcome.evaluator_name,
        evaluator_version=outcome.evaluator_version,
        score=score,
        threshold=threshold,
        status=EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED,
        reason=reason,
        evidence=(
            *outcome.evidence,
            EvaluationEvidence(
                label=CITATIONS_EVIDENCE_LABEL,
                value={
                    "required": len(expectation.require),
                    "missing": [
                        {"source": required.source, "segment": required.segment}
                        for required in missing
                    ],
                    "checks": len(checks),
                    "verified": len(verified),
                    "unverified": unverified,
                    "on_unverified": expectation.on_unverified,
                },
            ),
        ),
    )


def unreadable_citations(
    outcome: EvaluationResult,
    message: str,
) -> EvaluationResult:
    """Return a case's evaluation failed because its run's checks cannot be read."""

    score, threshold = _failing(0.0, outcome.threshold, 0.0)

    return EvaluationResult(
        id=outcome.id,
        evaluator_name=outcome.evaluator_name,
        evaluator_version=outcome.evaluator_version,
        score=score,
        threshold=threshold,
        status=EvaluationStatus.FAILED,
        reason=f"{outcome.reason} Citations cannot be judged: {message}",
        evidence=outcome.evidence,
    )


def _failing(
    score: float,
    threshold: float,
    fraction: float,
) -> tuple[float, float]:
    """Return a score and threshold that fail, for a case its citations failed.

    A score still at its threshold is brought below it by the fraction of
    citations met. A threshold of 0, which every score meets, becomes 1.
    """

    failing_threshold = threshold if threshold > 0.0 else 1.0

    if score < failing_threshold:
        return score, failing_threshold

    return failing_threshold * fraction, failing_threshold


__all__ = [
    "CITATIONS_EVIDENCE_LABEL",
    "CitationEvidenceError",
    "judge_citations",
    "recorded_citation_checks",
    "unreadable_citations",
]
