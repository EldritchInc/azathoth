"""Step confidence: how sure a step is of what it produced (ADR 0098)."""

import json
from uuid import UUID

from pydantic import JsonValue

MIN_CONFIDENCE = 0.0
"""The lowest confidence a step may report."""

MAX_CONFIDENCE = 1.0
"""The highest confidence a step may report."""


class WorkflowStepConfidenceError(ValueError):
    """Raised when a step's declared confidence output is not a valid confidence.

    It fails the attempt, which is retried under the step's retry policy.
    """


def step_confidence(
    step_id: UUID,
    name: str,
    value: JsonValue,
) -> float:
    """Return one step's confidence from the value of its confidence output.

    A confidence is a JSON number from 0 to 1, inclusive. An integer is
    accepted; a boolean is not a number here.

    Raises:
        WorkflowStepConfidenceError: The value is not a number from 0 to 1.
    """

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not MIN_CONFIDENCE <= value <= MAX_CONFIDENCE
    ):
        raise WorkflowStepConfidenceError(
            f"Workflow step {step_id} confidence {name!r} must be a number from 0 to 1; "
            f"got {_describe(value)}."
        )

    return float(value)


def _describe(
    value: JsonValue,
) -> str:
    """Return one value as JSON, for an error message."""

    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except ValueError:
        return repr(value)


__all__ = [
    "MAX_CONFIDENCE",
    "MIN_CONFIDENCE",
    "WorkflowStepConfidenceError",
    "step_confidence",
]
