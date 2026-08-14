"""Deterministic verification of durable tool implementations."""

from time import perf_counter

from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.protocols import ToolExecutor
from azathoth.tools.testing import ToolTestCase
from azathoth.tools.verification import ToolTestResult, ToolVerification


class ToolVerifier:
    """Verify tool implementations against durable test cases."""

    def __init__(self, executor: ToolExecutor) -> None:
        self._executor = executor

    async def verify(
        self,
        implementation: ToolImplementation,
        test_cases: tuple[ToolTestCase, ...],
    ) -> ToolVerification:
        """Execute every test case and return deterministic verification."""

        results = tuple(
            [
                await self._verify_test_case(
                    implementation,
                    test_case,
                )
                for test_case in test_cases
            ]
        )

        return ToolVerification(
            implementation_id=implementation.id,
            results=results,
        )

    async def _verify_test_case(
        self,
        implementation: ToolImplementation,
        test_case: ToolTestCase,
    ) -> ToolTestResult:
        """Execute one test case and compare its structured output."""

        started_at = perf_counter()

        actual_output = await self._executor.execute(
            implementation,
            test_case.inputs,
        )

        duration_seconds = perf_counter() - started_at

        return ToolTestResult(
            test_case_id=test_case.id,
            passed=actual_output == test_case.expected_output,
            expected_output=test_case.expected_output,
            actual_output=actual_output,
            duration_seconds=duration_seconds,
        )
