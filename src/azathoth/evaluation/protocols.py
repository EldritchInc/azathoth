"""Protocols implemented by Azathoth evaluators."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from azathoth.evaluation.models import EvaluationResult, ExpectedOutcome


class EvaluatorMetadata(BaseModel):
    """Stable identifying information for an evaluator."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)


class Evaluator(Protocol):
    """A component that compares an actual result with an expectation."""

    @property
    def metadata(self) -> EvaluatorMetadata:
        """Return stable identifying metadata for this evaluator."""

        ...

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        """Evaluate an actual value against an expected outcome."""

        ...
