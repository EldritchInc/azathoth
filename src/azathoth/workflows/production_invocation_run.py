"""Associate production invocations with empirical workflow runs."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class ProductionInvocationRun(BaseModel):
    """Associate one production invocation with its workflow run."""

    model_config = ConfigDict(frozen=True)

    invocation_id: UUID
    run_id: UUID
    created_at: datetime = Field(default_factory=utc_now)
