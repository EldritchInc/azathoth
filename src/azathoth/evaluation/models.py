"""Domain models describing expected optimization outcomes."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class OutcomeComparison(StrEnum):
    """The broad comparison method appropriate for an expected outcome."""

    EXACT = "exact"
    SEMANTIC = "semantic"
    SCHEMA = "schema"


class ExpectedOutcome(BaseModel):
    """A result that a candidate strategy is expected to produce."""

    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1)
    value: JsonValue
    comparison: OutcomeComparison
