"""Workflow failure policy models."""

from enum import StrEnum


class WorkflowFailurePolicy(StrEnum):
    """Behavior applied when a workflow step exhausts its retries."""

    FAIL_WORKFLOW = "fail_workflow"
    CONTINUE = "continue"
    SKIP_DEPENDENTS = "skip_dependents"
