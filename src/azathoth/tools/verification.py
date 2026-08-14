"""Domain models describing tool implementation verification."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ToolTestResult(BaseModel):
    """Describe the result of executing one durable tool test case."""

    model_config = ConfigDict(frozen=True)

    test_case_id: UUID
    passed: bool
    expected_output: dict[str, JsonValue]
    actual_output: dict[str, JsonValue]
    duration_seconds: float = Field(ge=0.0)


class ToolVerification(BaseModel):
    """Describe deterministic verification of a tool implementation."""

    model_config = ConfigDict(frozen=True)

    implementation_id: UUID
    results: tuple[ToolTestResult, ...] = ()
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed_count(self) -> int:
        """Return the number of passing test results."""

        return sum(result.passed for result in self.results)

    @property
    def failed_count(self) -> int:
        """Return the number of failing test results."""

        return len(self.results) - self.passed_count

    @property
    def pass_rate(self) -> float:
        """Return the fraction of verification tests that passed."""

        if not self.results:
            return 0.0

        return self.passed_count / len(self.results)

    @property
    def passed(self) -> bool:
        """Return whether every verification test passed."""

        return bool(self.results) and self.failed_count == 0
