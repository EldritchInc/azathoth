"""Immutable production workflow invocation contracts."""

import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from azathoth.context import (
    Context,
    ContextEvent,
)
from azathoth.inputs import (
    JSON_MEDIA_TYPE,
    InputProvenance,
    ResolvedInput,
)
from azathoth.workflows.input import create_workflow_input_events

PRODUCTION_INVOCATION_EVENT_TYPE = "production.invocation.received"
PRODUCTION_INVOCATION_PRODUCER = "azathoth.production"

MAX_IDEMPOTENCY_KEY_LENGTH = 255
"""The most characters an idempotency key may hold (ADR 0097)."""

REQUEST_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
"""A request digest is a lowercase hex SHA-256 (ADR 0097)."""


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


def validate_idempotency_key(
    key: str,
) -> str:
    """Return one idempotency key, or raise if it is not one.

    A key holds 1 to 255 characters and no control characters. It is
    otherwise opaque (ADR 0097).

    Raises:
        ValueError: The key is empty, too long, or holds a control character.
    """

    if not key:
        raise ValueError("An idempotency key must not be empty.")

    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError(
            f"An idempotency key holds at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters; "
            f"got {len(key)}."
        )

    if any(unicodedata.category(character) == "Cc" for character in key):
        raise ValueError("An idempotency key must not hold control characters.")

    return key


class InvocationIdempotency(BaseModel):
    """The idempotency key and request digest one invocation was started with.

    An invocation started through a job envelope records both, so a retry of
    the same request finds it, and a different request under the same key is
    told apart (ADR 0097).
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    key: str
    request_digest: str = Field(pattern=REQUEST_DIGEST_PATTERN)

    @field_validator("key")
    @classmethod
    def check_key(
        cls,
        key: str,
    ) -> str:
        """Require a valid idempotency key."""

        return validate_idempotency_key(key)


class ProductionInvocation(BaseModel):
    """Identify one external call against one production workflow.

    An invocation started through a job envelope carries its idempotency;
    one started otherwise carries none.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    initial_context: Context
    caller_metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
    )
    created_at: datetime = Field(default_factory=utc_now)
    idempotency: InvocationIdempotency | None = None


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
    workflow_id: UUID,
    payload: JsonValue,
    caller_metadata: Mapping[str, JsonValue] | None = None,
    input_provenance: InputProvenance | None = None,
    idempotency: InvocationIdempotency | None = None,
) -> ProductionInvocation:
    """Create one production invocation from caller-supplied input.

    The input is recorded twice at the invocation's creation time: once as
    the production invocation event, and once as the canonical workflow input
    event that benchmark cases also emit. A workflow whose prompt binds the
    workflow input therefore renders identically when optimized against a
    benchmark and when invoked in production.

    When the input was resolved from a reference, its provenance follows as
    a `workflow.input.resolved` event (ADR 0096). An invocation started
    through a job envelope records its idempotency (ADR 0097).
    """

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
            *create_workflow_input_events(
                ResolvedInput(
                    value=payload,
                    media_type=(
                        input_provenance.media_type
                        if input_provenance is not None
                        else JSON_MEDIA_TYPE
                    ),
                    provenance=input_provenance,
                ),
                producer=PRODUCTION_INVOCATION_PRODUCER,
                occurred_at=created_at,
            ),
        )
    )

    return ProductionInvocation(
        id=invocation_id,
        workflow_id=workflow_id,
        initial_context=initial_context,
        caller_metadata=(dict(caller_metadata) if caller_metadata is not None else {}),
        created_at=created_at,
        idempotency=idempotency,
    )
