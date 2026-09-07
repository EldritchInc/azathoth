"""CLI verification of durable tool implementations."""

import asyncio
import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.tools import (
    PythonToolExecutor,
    SQLiteToolRepository,
    ToolExecutionError,
    ToolImplementation,
    ToolTestCase,
    ToolVerification,
    ToolVerifier,
)


def verify_tool(
    tool_id: UUID,
    *,
    version: str,
) -> int:
    """Verify every implementation for one exact tool definition version."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteToolRepository(
        configuration.database,
    )

    definition = repository.get_definition(
        tool_id,
        version,
    )

    if definition is None:
        print(
            f"Tool {tool_id}@{version} is not configured.",
            file=sys.stderr,
        )

        return 1

    implementations = tuple(
        implementation
        for implementation in repository.implementations()
        if (implementation.tool_id == tool_id and implementation.tool_version == version)
    )

    if not implementations:
        print(
            f"Tool {tool_id}@{version} has no implementations.",
            file=sys.stderr,
        )

        return 1

    test_cases = tuple(
        test_case for test_case in repository.test_cases() if test_case.tool_id == tool_id
    )

    if not test_cases:
        print(
            f"Tool {tool_id} has no test cases.",
            file=sys.stderr,
        )

        return 1

    verifier = ToolVerifier(
        PythonToolExecutor(),
    )

    all_passed = True

    for index, implementation in enumerate(
        implementations,
    ):
        if index:
            print()

        passed = _verify_implementation(
            verifier=verifier,
            implementation=implementation,
            test_cases=test_cases,
        )

        all_passed = all_passed and passed

    return 0 if all_passed else 1


def _verify_implementation(
    *,
    verifier: ToolVerifier,
    implementation: ToolImplementation,
    test_cases: tuple[ToolTestCase, ...],
) -> bool:
    """Verify and render one durable implementation."""

    print(f"Implementation ID: {implementation.id}")
    print(f"Implementation Version: {implementation.version}")
    print(f"Runtime: {implementation.runtime}")

    try:
        verification = asyncio.run(
            verifier.verify(
                implementation,
                test_cases,
            )
        )
    except ToolExecutionError as exc:
        print("Status: error")
        print(f"Error: {exc}")

        return False

    _print_verification(
        verification,
    )

    return verification.passed


def _print_verification(
    verification: ToolVerification,
) -> None:
    """Render deterministic verification evidence."""

    print(f"Status: {'passed' if verification.passed else 'failed'}")

    print(f"Tests: {len(verification.results)}")
    print(f"Passed: {verification.passed_count}")
    print(f"Failed: {verification.failed_count}")
    print(f"Pass Rate: {verification.pass_rate:.6f}")

    for result in verification.results:
        print()

        print(f"  Test Case ID: {result.test_case_id}")
        print(f"  Status: {'passed' if result.passed else 'failed'}")
        print(f"  Duration: {result.duration_seconds:.6f}s")

        if not result.passed:
            print(f"  Expected: {result.expected_output}")
            print(f"  Actual: {result.actual_output}")


__all__ = [
    "verify_tool",
]
