"""End-to-end tests for durable tool execution and verification."""

import asyncio
from uuid import UUID

from azathoth.tools import (
    PythonToolExecutor,
    ToolDefinition,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    ToolTestCase,
    ToolVerification,
    ToolVerifier,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")
IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")
FIRST_TEST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")
THIRD_TEST_CASE_ID = UUID("55555555-5555-5555-5555-555555555555")


def create_definition() -> ToolDefinition:
    """Create a deterministic word-count tool definition."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count whitespace-delimited words in text.",
        version="1.0.0",
        input_schema=ToolInputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                    },
                },
                "required": ["text"],
            },
        ),
        output_schema=ToolOutputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                    },
                },
                "required": ["count"],
            },
        ),
    )


def create_implementation() -> ToolImplementation:
    """Create a deterministic Python word-count implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        entrypoint="run",
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def create_test_cases() -> tuple[ToolTestCase, ...]:
    """Create deterministic verification cases."""

    return (
        ToolTestCase(
            id=FIRST_TEST_CASE_ID,
            tool_id=TOOL_ID,
            name="counts two words",
            description="Verify a two-word input.",
            inputs={
                "text": "hello world",
            },
            expected_output={
                "count": 2,
            },
        ),
        ToolTestCase(
            id=SECOND_TEST_CASE_ID,
            tool_id=TOOL_ID,
            name="counts one word",
            description="Verify a one-word input.",
            inputs={
                "text": "hello",
            },
            expected_output={
                "count": 1,
            },
        ),
        ToolTestCase(
            id=THIRD_TEST_CASE_ID,
            tool_id=TOOL_ID,
            name="counts empty input",
            description="Verify empty input produces zero words.",
            inputs={
                "text": "",
            },
            expected_output={
                "count": 0,
            },
        ),
    )


def test_tool_execution_verifies_real_python_implementation() -> None:
    definition = create_definition()
    implementation = create_implementation()
    test_cases = create_test_cases()

    assert implementation.tool_id == definition.id
    assert implementation.tool_version == definition.version
    assert all(test_case.tool_id == definition.id for test_case in test_cases)

    verifier = ToolVerifier(PythonToolExecutor())

    verification = asyncio.run(
        verifier.verify(
            implementation,
            test_cases,
        )
    )

    assert verification.implementation_id == IMPLEMENTATION_ID
    assert tuple(result.test_case_id for result in verification.results) == (
        FIRST_TEST_CASE_ID,
        SECOND_TEST_CASE_ID,
        THIRD_TEST_CASE_ID,
    )
    assert tuple(result.actual_output for result in verification.results) == (
        {
            "count": 2,
        },
        {
            "count": 1,
        },
        {
            "count": 0,
        },
    )
    assert verification.passed_count == 3
    assert verification.failed_count == 0
    assert verification.pass_rate == 1.0
    assert verification.passed is True


def test_tool_definition_round_trips_before_execution() -> None:
    definition = create_definition()

    restored = ToolDefinition.model_validate_json(
        definition.model_dump_json(),
    )

    assert restored == definition


def test_tool_implementation_round_trips_before_execution() -> None:
    implementation = create_implementation()

    restored = ToolImplementation.model_validate_json(
        implementation.model_dump_json(),
    )

    verifier = ToolVerifier(PythonToolExecutor())
    verification = asyncio.run(
        verifier.verify(
            restored,
            create_test_cases(),
        )
    )

    assert restored == implementation
    assert verification.passed is True
    assert verification.pass_rate == 1.0


def test_tool_test_cases_round_trip_before_execution() -> None:
    implementation = create_implementation()

    restored_test_cases = tuple(
        ToolTestCase.model_validate_json(
            test_case.model_dump_json(),
        )
        for test_case in create_test_cases()
    )

    verifier = ToolVerifier(PythonToolExecutor())
    verification = asyncio.run(
        verifier.verify(
            implementation,
            restored_test_cases,
        )
    )

    assert restored_test_cases == create_test_cases()
    assert verification.passed_count == 3
    assert verification.failed_count == 0
    assert verification.passed is True


def test_tool_verification_round_trips_after_execution() -> None:
    verifier = ToolVerifier(PythonToolExecutor())

    verification = asyncio.run(
        verifier.verify(
            create_implementation(),
            create_test_cases(),
        )
    )

    restored = ToolVerification.model_validate_json(
        verification.model_dump_json(),
    )

    assert restored == verification
    assert restored.passed_count == 3
    assert restored.failed_count == 0
    assert restored.pass_rate == 1.0
    assert restored.passed is True


def test_complete_durable_tool_lifecycle_round_trips() -> None:
    definition = create_definition()
    implementation = create_implementation()
    test_cases = create_test_cases()

    restored_definition = ToolDefinition.model_validate_json(
        definition.model_dump_json(),
    )
    restored_implementation = ToolImplementation.model_validate_json(
        implementation.model_dump_json(),
    )
    restored_test_cases = tuple(
        ToolTestCase.model_validate_json(
            test_case.model_dump_json(),
        )
        for test_case in test_cases
    )

    verifier = ToolVerifier(PythonToolExecutor())

    verification = asyncio.run(
        verifier.verify(
            restored_implementation,
            restored_test_cases,
        )
    )

    restored_verification = ToolVerification.model_validate_json(
        verification.model_dump_json(),
    )

    assert restored_definition == definition
    assert restored_implementation == implementation
    assert restored_test_cases == test_cases

    assert restored_implementation.tool_id == restored_definition.id
    assert restored_implementation.tool_version == restored_definition.version
    assert all(test_case.tool_id == restored_definition.id for test_case in restored_test_cases)

    assert restored_verification.implementation_id == restored_implementation.id
    assert restored_verification.passed_count == 3
    assert restored_verification.failed_count == 0
    assert restored_verification.pass_rate == 1.0
    assert restored_verification.passed is True
