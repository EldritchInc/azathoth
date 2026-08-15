"""Tests for durable tool requirement models."""

import pytest
from pydantic import ValidationError

from azathoth.tools import (
    ToolRequirement,
    ToolRequirementMatch,
    ToolRequirements,
)


def test_tool_requirement_records_fields() -> None:
    requirement = ToolRequirement(
        name="word_count",
        version="1.0.0",
        runtime="python",
    )

    assert requirement.name == "word_count"
    assert requirement.version == "1.0.0"
    assert requirement.runtime == "python"


def test_tool_requirement_defaults_optional_fields() -> None:
    requirement = ToolRequirement(
        name="word_count",
    )

    assert requirement.version is None
    assert requirement.runtime is None


def test_tool_requirement_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ToolRequirement(
            name="",
        )


def test_tool_requirement_is_immutable() -> None:
    requirement = ToolRequirement(
        name="word_count",
    )

    with pytest.raises(ValidationError):
        requirement.name = "sentence_count"


def test_tool_requirements_defaults_empty() -> None:
    requirements = ToolRequirements()

    assert requirements.requirements == ()


def test_tool_requirements_records_requirements() -> None:
    requirement = ToolRequirement(
        name="word_count",
    )

    requirements = ToolRequirements(
        requirements=(requirement,),
    )

    assert requirements.requirements == (requirement,)


def test_tool_requirements_is_immutable() -> None:
    requirements = ToolRequirements()

    with pytest.raises(ValidationError):
        requirements.requirements = ()


def test_tool_requirement_match_records_match() -> None:
    requirement = ToolRequirement(
        name="word_count",
    )

    match = ToolRequirementMatch(
        requirement=requirement,
        matched=True,
    )

    assert match.requirement == requirement
    assert match.matched is True


def test_tool_requirement_match_is_immutable() -> None:
    requirement = ToolRequirement(
        name="word_count",
    )

    match = ToolRequirementMatch(
        requirement=requirement,
        matched=True,
    )

    with pytest.raises(ValidationError):
        match.matched = False


def test_tool_requirements_round_trip_json() -> None:
    requirements = ToolRequirements(
        requirements=(
            ToolRequirement(
                name="word_count",
                runtime="python",
            ),
        ),
    )

    restored = ToolRequirements.model_validate_json(
        requirements.model_dump_json(),
    )

    assert restored == requirements
