"""Domain models describing reusable evaluation benchmarks."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from azathoth.evaluation.json_equality import json_values_equal
from azathoth.evaluation.models import ExpectedOutcome, OutcomeComparison


class BenchmarkCaseConflictError(ValueError):
    """Raised when a benchmark already contains an equivalent case."""


class BenchmarkCase(BaseModel):
    """One input and expected outcome in an evaluation benchmark."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    input: JsonValue
    expected: ExpectedOutcome
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class BenchmarkDataset(BaseModel):
    """An immutable collection of reusable benchmark cases."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    cases: tuple[BenchmarkCase, ...] = ()

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> "BenchmarkDataset":
        """Reject duplicate benchmark case identifiers."""

        case_ids = tuple(case.id for case in self.cases)

        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Benchmark dataset cannot contain duplicate case identifiers.")

        return self

    def with_case(
        self,
        case: BenchmarkCase,
    ) -> "BenchmarkDataset":
        """Return this dataset with one more case appended after every existing case.

        The dataset itself is unchanged, so the result can be saved as the
        benchmark's next revision. Cases may share an input when they expect
        different outcomes, because a judged comparison can accept more than
        one result for the same input.

        Raises:
            BenchmarkCaseConflictError: An existing case has a JSON-equal
                input, the same comparison, and a JSON-equal expected value.
            ValueError: The case reuses an existing case identifier.
        """

        for existing in self.cases:
            if (
                existing.expected.comparison is case.expected.comparison
                and json_values_equal(existing.input, case.input)
                and json_values_equal(existing.expected.value, case.expected.value)
            ):
                raise BenchmarkCaseConflictError(
                    f"Benchmark dataset {self.id} already contains case {existing.id} "
                    "with this input and expected outcome."
                )

        return BenchmarkDataset.model_validate(
            {
                **dict(self),
                "cases": (*self.cases, case),
            }
        )

    def uses_comparison(
        self,
        comparison: OutcomeComparison,
    ) -> bool:
        """Return whether any case is judged with one comparison."""

        return any(case.expected.comparison is comparison for case in self.cases)

    def comparison_counts(
        self,
    ) -> dict[OutcomeComparison, int]:
        """Return how many cases use each comparison, in declaration order.

        Comparisons used by no case are omitted.
        """

        counts = {
            comparison: sum(case.expected.comparison is comparison for case in self.cases)
            for comparison in OutcomeComparison
        }

        return {comparison: count for comparison, count in counts.items() if count}
