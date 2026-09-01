"""Resolve workflow experiment evidence against executable candidates."""

from collections.abc import Sequence

from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateSignature,
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
)


def resolve_workflow_candidate(
    *,
    signature: WorkflowCandidateSignature,
    candidates: Sequence[WorkflowCandidate],
) -> WorkflowCandidate:
    """Resolve exactly one executable workflow candidate by signature."""

    matches = tuple(candidate for candidate in candidates if candidate.signature == signature)

    if not matches:
        raise ValueError(
            "Workflow experiment evidence does not match any supplied workflow candidate."
        )

    if len(matches) > 1:
        raise ValueError(
            "Workflow experiment evidence matches multiple supplied workflow candidates."
        )

    return matches[0]


def resolve_workflow_experiment_evidence(
    *,
    evidence: WorkflowExperimentEvidence,
    candidates: Sequence[WorkflowCandidate],
) -> WorkflowCandidate:
    """Resolve one experiment evidence item to its executable candidate."""

    return resolve_workflow_candidate(
        signature=evidence.candidate_signature,
        candidates=candidates,
    )


def resolve_workflow_experiment_winner(
    *,
    experiment: WorkflowExperimentResult,
    candidates: Sequence[WorkflowCandidate],
) -> WorkflowCandidate:
    """Resolve the highest-ranked experiment evidence to its executable candidate."""

    return resolve_workflow_experiment_evidence(
        evidence=experiment.winner_evidence,
        candidates=candidates,
    )
