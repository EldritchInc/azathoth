"""Rendering where a recorded run came from (ADR 0104)."""

from azathoth.context import Context, lineage_of


def render_lineage_lines(
    context: Context,
) -> list[str]:
    """Return the lines naming the lineage an initial context records.

    A root run's context records none, and renders no lines.

    Raises:
        LineageError: The recorded lineage is not valid lineage.
    """

    lineage = lineage_of(context)

    if lineage is None:
        return []

    return [
        f"Depth: {lineage.depth}",
        f"Parent Workflow ID: {lineage.parent.workflow_id}",
        f"Parent Run ID: {lineage.parent.run_id}",
        f"Parent Step ID: {lineage.parent.step_id} (attempt {lineage.parent.attempt})",
        f"Root Workflow ID: {lineage.root.workflow_id}",
        f"Root Run ID: {lineage.root.run_id}",
    ]


__all__ = [
    "render_lineage_lines",
]
