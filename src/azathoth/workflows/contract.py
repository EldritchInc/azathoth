"""Checking a production invocation against its workflow's declared schemas (ADR 0118).

A promoted workflow may declare the JSON Schema of the input it receives and
of the result it declares. Every production invocation is checked against
the promoted specification's schemas: its input before any run starts, and
its result once its run has produced it. A violation fails the invocation
with a stable code, a message naming every violation by its JSON path, and
the violations themselves as metadata.
"""

from typing import Final
from uuid import UUID

from pydantic import JsonValue

from azathoth.evaluation import json_schema_validator, json_schema_violations
from azathoth.workflows.production_invocation import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
)

VIOLATIONS_METADATA_KEY: Final = "violations"
"""The failure metadata naming each violation of a schema, by path and message."""


def input_contract_failure(
    *,
    invocation_id: UUID,
    schema: JsonValue | None,
    received: JsonValue,
) -> ProductionInvocationFailure | None:
    """Return the failure of an invocation whose input breaks its input schema, or None.

    The input checked is the value the workflow receives, after resolution,
    so a document is its content handle.
    """

    return _contract_failure(
        invocation_id=invocation_id,
        schema=schema,
        value=received,
        code=ProductionInvocationErrorCode.INVALID_INPUT,
        described="The workflow's input does not match its input schema",
    )


def output_contract_failure(
    *,
    invocation_id: UUID,
    schema: JsonValue | None,
    result: JsonValue,
) -> ProductionInvocationFailure | None:
    """Return the failure of an invocation whose result breaks its output schema, or None."""

    return _contract_failure(
        invocation_id=invocation_id,
        schema=schema,
        value=result,
        code=ProductionInvocationErrorCode.INVALID_OUTPUT,
        described="The workflow's result does not match its output schema",
    )


def _contract_failure(
    *,
    invocation_id: UUID,
    schema: JsonValue | None,
    value: JsonValue,
    code: ProductionInvocationErrorCode,
    described: str,
) -> ProductionInvocationFailure | None:
    """Return the failure of a value that breaks a schema, or None when it keeps it."""

    if schema is None:
        return None

    violations = json_schema_violations(json_schema_validator(schema), value)

    if not violations:
        return None

    return ProductionInvocationFailure(
        invocation_id=invocation_id,
        error_code=code,
        message=(
            f"{described}: "
            + "; ".join(f"{violation.path}: {violation.message}" for violation in violations)
            + "."
        ),
        metadata={
            VIOLATIONS_METADATA_KEY: [
                {"path": violation.path, "message": violation.message} for violation in violations
            ]
        },
    )


__all__ = [
    "VIOLATIONS_METADATA_KEY",
    "input_contract_failure",
    "output_contract_failure",
]
