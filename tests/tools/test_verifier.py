"""Tests for deterministic tool implementation verification."""

import asyncio
from uuid import UUID

from pydantic import JsonValue

from azathoth.tools import (
    ToolImplementation,
    ToolTestCase,
    ToolVerifier,
)

IMPLEMENTATION_ID = UUID("11111111-1111-1111-1111-111111111111")
TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")
FIRST_TEST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


class CountingExecutor:
    """Return deterministic word counts for verification."""

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Count whitespace-delimited words."""

        text = inputs["text"]

        if not isinstance(text, str):
            raise TypeError("text must be a string")

        return {
            "count": len(text.split()),
        }


def create_implementation() -> ToolImplementation:
    """Create a deterministic tool implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime="python",
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def create_test_case(
    *,
    test_case_id: UUID = FIRST_TEST_CASE_ID,
    text: str = "hello world",
    expected_count: int = 2,
) -> ToolTestCase:
    """Create a deterministic tool test case."""

    return ToolTestCase(
        id=test_case_id,
        tool_id=TOOL_ID,
        name="word count",
        description="Verify deterministic word counting.",
        inputs={
            "text": text,
        },
        expected_output={
            "count": expected_count,
        },
    )


def test_tool_verifier_verifies_passing_test_case() -> None:
    verifier = ToolVerifier(CountingExecutor())
    implementation = create_implementation()
    test_case = create_test_case()

    verification = asyncio.run(
        verifier.verify(
            implementation,
            (test_case,),
        )
    )

    assert verification.implementation_id == IMPLEMENTATION_ID
    assert len(verification.results) == 1

    result = verification.results[0]

    assert result.test_case_id == FIRST_TEST_CASE_ID
    assert result.passed is True
    assert result.expected_output == {
        "count": 2,
    }
    assert result.actual_output == {
        "count": 2,
    }
    assert result.duration_seconds >= 0.0

    assert verification.passed_count == 1
    assert verification.failed_count == 0
    assert verification.pass_rate == 1.0
    assert verification.passed is True


def test_tool_verifier_records_failing_test_case() -> None:
    verifier = ToolVerifier(CountingExecutor())
    implementation = create_implementation()
    test_case = create_test_case(
        expected_count=3,
    )

    verification = asyncio.run(
        verifier.verify(
            implementation,
            (test_case,),
        )
    )

    result = verification.results[0]

    assert result.passed is False
    assert result.expected_output == {
        "count": 3,
    }
    assert result.actual_output == {
        "count": 2,
    }

    assert verification.passed_count == 0
    assert verification.failed_count == 1
    assert verification.pass_rate == 0.0
    assert verification.passed is False


def test_tool_verifier_verifies_multiple_test_cases() -> None:
    verifier = ToolVerifier(CountingExecutor())
    implementation = create_implementation()
    first = create_test_case()
    second = create_test_case(
        test_case_id=SECOND_TEST_CASE_ID,
        text="one two three",
        expected_count=3,
    )

    verification = asyncio.run(
        verifier.verify(
            implementation,
            (
                first,
                second,
            ),
        )
    )

    assert tuple(result.test_case_id for result in verification.results) == (
        FIRST_TEST_CASE_ID,
        SECOND_TEST_CASE_ID,
    )
    assert verification.passed_count == 2
    assert verification.failed_count == 0
    assert verification.pass_rate == 1.0
    assert verification.passed is True


def test_tool_verifier_computes_mixed_results() -> None:
    verifier = ToolVerifier(CountingExecutor())
    implementation = create_implementation()
    first = create_test_case()
    second = create_test_case(
        test_case_id=SECOND_TEST_CASE_ID,
        text="one two three",
        expected_count=4,
    )

    verification = asyncio.run(
        verifier.verify(
            implementation,
            (
                first,
                second,
            ),
        )
    )

    assert tuple(result.passed for result in verification.results) == (
        True,
        False,
    )
    assert verification.passed_count == 1
    assert verification.failed_count == 1
    assert verification.pass_rate == 0.5
    assert verification.passed is False


def test_tool_verifier_handles_no_test_cases() -> None:
    verifier = ToolVerifier(CountingExecutor())
    implementation = create_implementation()

    verification = asyncio.run(
        verifier.verify(
            implementation,
            (),
        )
    )

    assert verification.implementation_id == IMPLEMENTATION_ID
    assert verification.results == ()
    assert verification.passed_count == 0
    assert verification.failed_count == 0
    assert verification.pass_rate == 0.0
    assert verification.passed is False
