"""Tests for deterministic tool matching."""

from uuid import UUID

from azathoth.tools import (
    ToolDefinition,
    ToolInputSchema,
    ToolMatcher,
    ToolOutputSchema,
    ToolRequirement,
    ToolRequirements,
)

WORD_COUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
SENTENCE_COUNT_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_input_schema() -> ToolInputSchema:
    """Create a deterministic input schema."""

    return ToolInputSchema(
        json_schema={
            "type": "object",
        },
    )


def create_output_schema() -> ToolOutputSchema:
    """Create a deterministic output schema."""

    return ToolOutputSchema(
        json_schema={
            "type": "object",
        },
    )


def create_definition(
    *,
    tool_id: UUID = WORD_COUNT_ID,
    name: str = "word_count",
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"{name} tool.",
        version=version,
        input_schema=create_input_schema(),
        output_schema=create_output_schema(),
    )


def test_matches_name() -> None:
    matcher = ToolMatcher()

    assert matcher.matches(
        create_definition(),
        ToolRequirement(
            name="word_count",
        ),
    )


def test_rejects_different_name() -> None:
    matcher = ToolMatcher()

    assert not matcher.matches(
        create_definition(),
        ToolRequirement(
            name="sentence_count",
        ),
    )


def test_matches_specific_version() -> None:
    matcher = ToolMatcher()

    assert matcher.matches(
        create_definition(version="2.0.0"),
        ToolRequirement(
            name="word_count",
            version="2.0.0",
        ),
    )


def test_rejects_wrong_version() -> None:
    matcher = ToolMatcher()

    assert not matcher.matches(
        create_definition(version="1.0.0"),
        ToolRequirement(
            name="word_count",
            version="2.0.0",
        ),
    )


def test_match_records_success() -> None:
    matcher = ToolMatcher()

    matches = matcher.match(
        definitions=(
            create_definition(),
            create_definition(
                tool_id=SENTENCE_COUNT_ID,
                name="sentence_count",
            ),
        ),
        requirements=ToolRequirements(
            requirements=(
                ToolRequirement(
                    name="word_count",
                ),
            ),
        ),
    )

    assert len(matches) == 1
    assert matches[0].matched is True


def test_match_records_failure() -> None:
    matcher = ToolMatcher()

    matches = matcher.match(
        definitions=(create_definition(),),
        requirements=ToolRequirements(
            requirements=(
                ToolRequirement(
                    name="translation",
                ),
            ),
        ),
    )

    assert len(matches) == 1
    assert matches[0].matched is False


def test_multiple_requirements() -> None:
    matcher = ToolMatcher()

    matches = matcher.match(
        definitions=(
            create_definition(),
            create_definition(
                tool_id=SENTENCE_COUNT_ID,
                name="sentence_count",
            ),
        ),
        requirements=ToolRequirements(
            requirements=(
                ToolRequirement(
                    name="word_count",
                ),
                ToolRequirement(
                    name="sentence_count",
                ),
                ToolRequirement(
                    name="translation",
                ),
            ),
        ),
    )

    assert tuple(match.matched for match in matches) == (
        True,
        True,
        False,
    )


def test_empty_requirements() -> None:
    matcher = ToolMatcher()

    matches = matcher.match(
        definitions=(create_definition(),),
        requirements=ToolRequirements(),
    )

    assert matches == ()
