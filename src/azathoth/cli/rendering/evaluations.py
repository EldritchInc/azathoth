"""Human-readable workflow run evaluation rendering."""

import json
from collections.abc import Sequence

from azathoth.workflows import WorkflowRunEvaluation


def render_workflow_run_evaluations(
    evaluations: Sequence[WorkflowRunEvaluation],
) -> str:
    """Render every evaluator judgment recorded for one run, in the order given.

    Each evidence item renders on one line as its label and compact JSON value.
    """

    if not evaluations:
        return "Evaluations: none"

    lines = [f"Evaluations: {len(evaluations)}"]

    for index, record in enumerate(
        evaluations,
        start=1,
    ):
        evaluation = record.evaluation

        lines.extend(
            (
                "",
                f"Evaluation {index}",
                f"ID: {record.id}",
                f"Evaluated: {record.evaluated_at.isoformat()}",
                f"Evaluator: {evaluation.evaluator_name} {evaluation.evaluator_version}",
                f"Status: {evaluation.status.value}",
                f"Score: {evaluation.score:.6f} (threshold {evaluation.threshold:.6f})",
                f"Reason: {evaluation.reason}",
            )
        )

        lines.extend(
            f"Evidence: {item.label} = {json.dumps(item.value, ensure_ascii=False)}"
            for item in evaluation.evidence
        )

    return "\n".join(lines)
