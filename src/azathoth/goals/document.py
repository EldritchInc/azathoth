"""JSON document serialization for durable reusable goals."""

from pydantic import ValidationError

from azathoth.goals.models import Goal


class GoalDocumentError(ValueError):
    """Raised when a goal document cannot be reconstructed."""


def encode_goal_document(
    goal: Goal,
) -> str:
    """Serialize one reusable goal as a readable JSON document."""

    return goal.model_dump_json(
        indent=2,
    )


def decode_goal_document(
    document: str,
) -> Goal:
    """Reconstruct one reusable goal from a JSON document."""

    try:
        return Goal.model_validate_json(
            document,
        )
    except ValidationError as exc:
        raise GoalDocumentError("Goal document is not a valid Goal.") from exc
