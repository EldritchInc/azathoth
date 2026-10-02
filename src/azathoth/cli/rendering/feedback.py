"""Human-readable workflow run feedback rendering."""

from collections.abc import Sequence

from azathoth.cli.rendering._json import render_json_value
from azathoth.workflows import WorkflowRunFeedback


def render_workflow_run_feedback(
    feedback: Sequence[WorkflowRunFeedback],
) -> str:
    """Render every judgment recorded for one run, in the order given."""

    if not feedback:
        return "Feedback: none"

    lines = [f"Feedback: {len(feedback)}"]

    for index, record in enumerate(
        feedback,
        start=1,
    ):
        lines.extend(
            (
                "",
                f"Feedback {index}",
                f"ID: {record.id}",
                f"Created: {record.created_at.isoformat()}",
                f"Disposition: {record.disposition.value}",
            )
        )

        if record.reason is not None:
            lines.append(f"Reason: {record.reason}")

        if record.corrected_output is not None:
            lines.extend(
                (
                    "Corrected Output:",
                    render_json_value(record.corrected_output),
                )
            )

    return "\n".join(lines)
