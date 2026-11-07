"""Domain models describing expected outcomes and completed evaluations."""

from enum import StrEnum
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from azathoth.evaluation.json_schema import json_schema_validator


class OutcomeComparison(StrEnum):
    """The broad comparison method appropriate for an expected outcome."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    SEMANTIC = "semantic"
    SCHEMA = "schema"


class EvaluationStatus(StrEnum):
    """The final status assigned to an evaluated result."""

    PASSED = "passed"
    FAILED = "failed"


class CitedSegment(BaseModel):
    """One segment of one source a result must cite, by the names a cited step uses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    segment: str = Field(min_length=1)


class CitationExpectation(BaseModel):
    """The citations a case's run must have made and verified (ADR 0117).

    Each required segment is met by a verified check, of that source and
    segment, that a cited step of the run kept. Under `on_unverified`
    `fail`, the default, any check the run kept that did not verify fails
    the case too; under `ignore`, only the required segments count.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    require: tuple[CitedSegment, ...] = ()
    on_unverified: Literal["fail", "ignore"] = "fail"

    @model_validator(mode="after")
    def reject_repeated_segments(self) -> "CitationExpectation":
        """Reject a segment required more than once.

        Raises:
            ValueError: Two required segments name the same source and segment.
        """

        seen: set[CitedSegment] = set()

        for cited in self.require:
            if cited in seen:
                raise ValueError(
                    f"Citation expectation requires segment {cited.segment} of source "
                    f"{cited.source!r} more than once."
                )

            seen.add(cited)

        return self


class ExpectedOutcome(BaseModel):
    """A result that a candidate strategy is expected to produce.

    `citations` names what the result's run must cite (ADR 0117). An outcome
    without it serializes without it, so no existing dataset's digest
    changes.
    """

    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1)
    value: JsonValue
    comparison: OutcomeComparison
    citations: CitationExpectation | None = None

    @model_serializer(mode="wrap")
    def omit_absent_citations(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out `citations` when the outcome names none."""

        serialized = cast(dict[str, JsonValue], handler(self))

        if self.citations is None:
            serialized.pop("citations", None)

        return serialized

    @model_validator(mode="after")
    def validate_schema_expectation(self) -> "ExpectedOutcome":
        """Reject schema expectations whose value is not a valid JSON Schema."""

        if self.comparison is OutcomeComparison.SCHEMA:
            json_schema_validator(self.value)

        return self


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
