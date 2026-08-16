"""Domain models describing reusable evaluation benchmarks."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from azathoth.evaluation.models import ExpectedOutcome


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
