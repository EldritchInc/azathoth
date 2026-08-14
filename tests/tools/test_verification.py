"""Tests for durable tool verification models."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.tools import ToolTestResult, ToolVerification

IMPLEMENTATION_ID = UUID("11111111-1111-1111-1111-111111111111")
FIRST_TEST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_TEST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")
VERIFIED_AT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def create_test_result(
    *,
    test_case_id: UUID = FIRST_TEST_CASE_ID,
    passed: bool = True,
) -> ToolTestResult:
    """Create a deterministic tool test result."""

    return ToolTestResult(
        test_case_id=test_case_id,
        passed=passed,
        expected_output={
            "count": 2,
        },
        actual_output={
            "count": 2 if passed else 3,
        },
        duration_seconds=0.01,
    )


def test_tool_test_result_records_execution() -> None:
    result = create_test_result()

    assert result.test_case_id == FIRST_TEST_CASE_ID
    assert result.passed is True
    assert result.expected_output == {
        "count": 2,
    }
    assert result.actual_output == {
        "count": 2,
    }
    assert result.duration_seconds == 0.01


def test_tool_test_result_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError):
        ToolTestResult(
            test_case_id=FIRST_TEST_CASE_ID,
            passed=True,
            expected_output={},
            actual_output={},
            duration_seconds=-1.0,
        )


def test_tool_test_result_is_immutable() -> None:
    result = create_test_result()

    with pytest.raises(ValidationError):
        result.passed = False


def test_tool_verification_records_results() -> None:
    first = create_test_result()
    second = create_test_result(
        test_case_id=SECOND_TEST_CASE_ID,
        passed=False,
    )
    verification = ToolVerification(
        implementation_id=IMPLEMENTATION_ID,
        results=(first, second),
        verified_at=VERIFIED_AT,
    )

    assert verification.implementation_id == IMPLEMENTATION_ID
    assert verification.results == (
        first,
        second,
    )
    assert verification.verified_at == VERIFIED_AT


def test_tool_verification_computes_passing_statistics() -> None:
    first = create_test_result()
    second = create_test_result(
        test_case_id=SECOND_TEST_CASE_ID,
    )
    verification = ToolVerification(
        implementation_id=IMPLEMENTATION_ID,
        results=(first, second),
        verified_at=VERIFIED_AT,
    )

    assert verification.passed_count == 2
    assert verification.failed_count == 0
    assert verification.pass_rate == 1.0
    assert verification.passed is True


def test_tool_verification_computes_mixed_statistics() -> None:
    first = create_test_result()
    second = create_test_result(
        test_case_id=SECOND_TEST_CASE_ID,
        passed=False,
    )
    verification = ToolVerification(
        implementation_id=IMPLEMENTATION_ID,
        results=(first, second),
        verified_at=VERIFIED_AT,
    )

    assert verification.passed_count == 1
    assert verification.failed_count == 1
    assert verification.pass_rate == 0.5
    assert verification.passed is False


def test_tool_verification_handles_no_results() -> None:
    verification = ToolVerification(
        implementation_id=IMPLEMENTATION_ID,
        results=(),
        verified_at=VERIFIED_AT,
    )

    assert verification.passed_count == 0
    assert verification.failed_count == 0
    assert verification.pass_rate == 0.0
    assert verification.passed is False


def test_tool_verification_is_immutable() -> None:
    verification = ToolVerification(
        implementation_id=IMPLEMENTATION_ID,
        verified_at=VERIFIED_AT,
    )

    with pytest.raises(ValidationError):
        verification.results = ()


def test_tool_verification_round_trips_through_json() -> None:
    verification = ToolVerification(
        implementation_id=IMPLEMENTATION_ID,
        results=(create_test_result(),),
        verified_at=VERIFIED_AT,
    )

    restored = ToolVerification.model_validate_json(
        verification.model_dump_json(),
    )

    assert restored == verification
