"""Tests for the checked-in portable goal example."""

from pathlib import Path
from uuid import UUID

from azathoth.goals import (
    Goal,
    decode_goal_document,
    encode_goal_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

ACCURATE_ANSWER_DOCUMENT = PROJECT_ROOT / "examples" / "goals" / "accurate-answer.json"

GOAL_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_expected_goal() -> Goal:
    """Create the goal represented by the checked-in example."""

    return Goal(
        id=GOAL_ID,
        name="Answer accurately",
        description=("Produce the correct answer for the supplied request."),
        success_criteria=(
            "The answer matches the expected result.",
            "The answer remains factual.",
        ),
        constraints=(
            "Do not rely on unavailable external state.",
            "Remain provider independent.",
        ),
    )


def test_checked_in_goal_example_decodes_to_expected_goal() -> None:
    encoded = ACCURATE_ANSWER_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert (
        decode_goal_document(
            encoded,
        )
        == create_expected_goal()
    )


def test_checked_in_goal_example_matches_canonical_encoding() -> None:
    encoded = ACCURATE_ANSWER_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encoded.rstrip("\n") == encode_goal_document(
        create_expected_goal(),
    )
