"""Executable workflow candidates."""

from dataclasses import dataclass

from azathoth.strategies import Strategy
from azathoth.workflows.models import WorkflowMetadata


@dataclass(frozen=True, slots=True)
class WorkflowCandidate:
    """An executable workflow generated from a workflow specification."""

    metadata: WorkflowMetadata
    steps: tuple[Strategy, ...]
