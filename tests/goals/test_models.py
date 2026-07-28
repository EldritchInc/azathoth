"""Tests for goal domain models."""

import pytest
from pydantic import ValidationError

from azathoth.goals import Goal


def test_goal_requires_success_criteria() -> None:
    with pytest.raises(ValidationError):
        Goal(
            name="Classify support requests",
            description="Identify the correct support request category.",
            success_criteria=(),
        )


def test_goal_is_immutable() -> None:
    goal = Goal(
        name="Classify support requests",
        description="Identify the correct support request category.",
        success_criteria=("The predicted category matches the expected category.",),
    )

    with pytest.raises(ValidationError):
        goal.name = "Changed goal"
