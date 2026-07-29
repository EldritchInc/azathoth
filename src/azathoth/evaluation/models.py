"""Domain models describing expected outcomes and completed evaluations."""

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)


class OutcomeComparison(StrEnum):
    """The broad comparison method appropriate for an expected outcome."""

    EXACT = "exact"
    SEMANTIC = "semantic"
    SCHEMA = "schema"


class EvaluationStatus(StrEnum):
    """The final status assigned to an evaluated result."""

    PASSED = "passed"
    FAILED = "failed"


class ExpectedOutcome(BaseModel):
    """A result that a candidate strategy is expected to produce."""

    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1)
    value: JsonValue
    comparison: OutcomeComparison


class EvaluationEvidence(BaseModel):
    """Structured evidence supporting an evaluator's conclusion."""

    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=1)
    value: JsonValue


class EvaluationResult(BaseModel):
    """The recorded result of evaluating one strategy output."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    evaluator_name: str = Field(min_length=1)
    evaluator_version: str = Field(default="1.0.0", min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(default=1.0, ge=0.0, le=1.0)
    status: EvaluationStatus
    reason: str = Field(min_length=1)
    evidence: tuple[EvaluationEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_status_matches_threshold(self) -> "EvaluationResult":
        """Ensure the recorded status agrees with the normalized score."""

        expected_status = (
            EvaluationStatus.PASSED if self.score >= self.threshold else EvaluationStatus.FAILED
        )

        if self.status is not expected_status:
            raise ValueError("Evaluation status must agree with score and threshold.")

        return self

    @property
    def passed(self) -> bool:
        """Return whether this evaluation passed."""

        return self.status is EvaluationStatus.PASSED
