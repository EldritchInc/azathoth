"""Human and application feedback attached to workflow run evidence."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class WorkflowRunFeedbackDisposition(StrEnum):
    """The disposition assigned to one completed workflow run."""

    GOOD = "good"
    BAD = "bad"


class WorkflowRunFeedback(BaseModel):
    """Record one immutable judgment about a completed workflow run."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    disposition: WorkflowRunFeedbackDisposition
    reason: str | None = None
    corrected_output: JsonValue = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_bad_feedback_has_reason(
        self,
    ) -> "WorkflowRunFeedback":
        """Require an explanation when a workflow run is marked bad."""

        if self.disposition is WorkflowRunFeedbackDisposition.BAD and (
            self.reason is None or not self.reason.strip()
        ):
            raise ValueError("Bad workflow run feedback requires a reason.")

        return self
