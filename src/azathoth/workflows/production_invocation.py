"""Immutable production workflow invocation contracts."""

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from azathoth.context import (
    Context,
    ContextEvent,
)
from azathoth.workflows.production import WorkflowProductionRevision

PRODUCTION_INVOCATION_EVENT_TYPE = "production.invocation.received"
PRODUCTION_INVOCATION_PRODUCER = "azathoth.production"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class ProductionInvocationErrorCode(StrEnum):
    """Stable externally meaningful production invocation failure categories."""

    WORKFLOW_NOT_DEPLOYED = "workflow_not_deployed"
    INVALID_INPUT = "invalid_input"
    MODEL_UNAVAILABLE = "model_unavailable"
    NO_APPROVED_MODEL_SUBSTITUTE = "no_approved_model_substitute"
    TOOL_UNAVAILABLE = "tool_unavailable"
    WORKFLOW_EXECUTION_FAILED = "workflow_execution_failed"
    TIMEOUT = "timeout"


class ProductionInvocation(BaseModel):
    """Identify one external call against one exact production revision."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    production_revision_id: UUID
    initial_context: Context
    caller_metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
    )
    created_at: datetime = Field(default_factory=utc_now)


class ProductionInvocationSuccess(BaseModel):
    """Represent the public successful result of one production invocation."""

    model_config = ConfigDict(frozen=True)

    invocation_id: UUID
    result: JsonValue


class ProductionInvocationFailure(BaseModel):
    """Represent the public failed result of one production invocation."""

    model_config = ConfigDict(frozen=True)

    invocation_id: UUID
    error_code: ProductionInvocationErrorCode
    message: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
    )


ProductionInvocationResult = ProductionInvocationSuccess | ProductionInvocationFailure


def create_production_invocation(
    *,
    revision: WorkflowProductionRevision,
    payload: JsonValue,
    caller_metadata: Mapping[str, JsonValue] | None = None,
) -> ProductionInvocation:
    """Create one production invocation from caller-supplied JSON input."""

    invocation_id = uuid4()
    created_at = utc_now()

    initial_context = Context(
        events=(
            ContextEvent(
                event_type=PRODUCTION_INVOCATION_EVENT_TYPE,
                payload={
                    "input": payload,
                },
                producer=PRODUCTION_INVOCATION_PRODUCER,
                occurred_at=created_at,
            ),
        )
    )

    return ProductionInvocation(
        id=invocation_id,
        workflow_id=revision.workflow_id,
        production_revision_id=revision.id,
        initial_context=initial_context,
        caller_metadata=(dict(caller_metadata) if caller_metadata is not None else {}),
        created_at=created_at,
    )
