"""Output formats of workflow execution commands."""

from enum import StrEnum


class WorkflowOutputFormat(StrEnum):
    """How `workflow run` and `workflow invoke` write their output.

    `jsonl` streams step records live on stdout and ends with exactly one
    terminal `result` or `error` record. `text` writes the human-readable
    report on stdout and step messages on stderr. `result` writes only the
    result value as JSON on stdout, for callers such as child workflows.
    """

    JSONL = "jsonl"
    TEXT = "text"
    RESULT = "result"


DEFAULT_WORKFLOW_OUTPUT_FORMAT = WorkflowOutputFormat.JSONL
"""The output format used when none is requested."""
