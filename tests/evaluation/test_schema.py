"""Tests for JSON Schema outcome evaluation."""

import asyncio

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    ExpectedOutcome,
    JsonSchemaViolation,
    OutcomeComparison,
    SchemaEvaluator,
    json_schema_validator,
    json_schema_violations,
)

TICKET_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {
        "category": {
            "enum": ["billing", "technical", "account"],
        },
        "priority": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["category", "priority"],
    "additionalProperties": False,
}


def evaluate(
    schema: JsonValue,
    actual: JsonValue,
) -> EvaluationResult:
    """Evaluate one actual value against one schema expectation."""

    return asyncio.run(
        SchemaEvaluator().evaluate(
            ExpectedOutcome(
                description="Schema expectation",
                value=schema,
                comparison=OutcomeComparison.SCHEMA,
            ),
            actual,
        )
    )


def test_schema_outcome_rejects_invalid_schema() -> None:
    with pytest.raises(ValidationError, match="Invalid JSON Schema"):
        ExpectedOutcome(
            description="Broken schema",
            value={"type": "not-a-type"},
            comparison=OutcomeComparison.SCHEMA,
        )


@pytest.mark.parametrize(
    "schema",
    (
        "object",
        1,
        None,
        ["type", "object"],
    ),
)
def test_schema_outcome_rejects_non_schema_values(
    schema: JsonValue,
) -> None:
    with pytest.raises(ValidationError, match="must be an object or a boolean"):
        ExpectedOutcome(
            description="Not a schema",
            value=schema,
            comparison=OutcomeComparison.SCHEMA,
        )


def test_non_schema_outcomes_do_not_require_schema_values() -> None:
    outcome = ExpectedOutcome(
        description="Exact value that resembles a broken schema",
        value={"type": "not-a-type"},
        comparison=OutcomeComparison.EXACT,
    )

    assert outcome.value == {"type": "not-a-type"}


def test_schema_dialect_follows_schema_keyword() -> None:
    validator = json_schema_validator(
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "items": [{"type": "string"}],
        }
    )

    assert json_schema_violations(validator, [1]) == (
        JsonSchemaViolation(
            path="$[0]",
            message="1 is not of type 'string'",
        ),
    )


def test_boolean_schemas_are_valid() -> None:
    assert evaluate(True, {"anything": [1, 2]}).passed
    assert not evaluate(False, "anything").passed


def test_schema_match_passes_for_conforming_value() -> None:
    actual: JsonValue = {
        "category": "billing",
        "priority": 2,
        "tags": ["refund"],
    }

    result = evaluate(TICKET_SCHEMA, actual)

    assert result.passed
    assert result.score == 1.0
    assert result.reason == "Actual value conformed to the expected schema."
    assert result.evidence == (
        EvaluationEvidence(label="schema", value=TICKET_SCHEMA),
        EvaluationEvidence(label="actual", value=actual),
    )


def test_schema_match_reports_violations_by_path() -> None:
    result = evaluate(
        TICKET_SCHEMA,
        {
            "category": "shipping",
            "priority": 9,
            "tags": ["ok", 3],
        },
    )

    assert not result.passed
    assert result.score == 0.0
    assert result.reason == "Actual value did not conform to the expected schema (3 violations)."
    assert result.evidence[2:] == (
        EvaluationEvidence(label="violation_count", value=3),
        EvaluationEvidence(
            label="violations",
            value=[
                {
                    "path": "$.category",
                    "message": "'shipping' is not one of ['billing', 'technical', 'account']",
                },
                {
                    "path": "$.priority",
                    "message": "9 is greater than the maximum of 5",
                },
                {
                    "path": "$.tags[1]",
                    "message": "3 is not of type 'string'",
                },
            ],
        ),
    )


def test_schema_match_reports_root_violations() -> None:
    result = evaluate(
        TICKET_SCHEMA,
        {"category": "billing", "extra": True},
    )

    assert result.reason == "Actual value did not conform to the expected schema (2 violations)."
    assert result.evidence[3] == EvaluationEvidence(
        label="violations",
        value=[
            {
                "path": "$",
                "message": "'priority' is a required property",
            },
            {
                "path": "$",
                "message": "Additional properties are not allowed ('extra' was unexpected)",
            },
        ],
    )


def test_schema_match_uses_singular_reason_for_one_violation() -> None:
    result = evaluate({"type": "integer"}, "7")

    assert result.reason == "Actual value did not conform to the expected schema (1 violation)."


def test_schema_match_does_not_accept_boolean_for_integer() -> None:
    assert not evaluate({"type": "integer"}, True).passed


def test_schema_match_records_at_most_ten_violations() -> None:
    result = evaluate(
        {"type": "array", "items": {"type": "string"}},
        list(range(12)),
    )

    assert result.evidence[2] == EvaluationEvidence(label="violation_count", value=12)

    violations = result.evidence[3].value

    assert isinstance(violations, list)
    assert len(violations) == 10


def test_schema_match_records_evaluator_identity() -> None:
    result = evaluate({"type": "string"}, "x")

    assert result.evaluator_name == "json-schema"
    assert result.evaluator_version == "1.0.0"
