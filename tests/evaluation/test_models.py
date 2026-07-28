"""Tests for evaluation domain models."""

from azathoth.evaluation import ExpectedOutcome, OutcomeComparison


def test_expected_outcome_supports_structured_values() -> None:
    outcome = ExpectedOutcome(
        description="The response contains the required support fields.",
        value={
            "required_fields": [
                "category",
                "customer_message",
                "recommended_action",
            ]
        },
        comparison=OutcomeComparison.SCHEMA,
    )

    assert outcome.comparison is OutcomeComparison.SCHEMA
    assert outcome.value == {
        "required_fields": [
            "category",
            "customer_message",
            "recommended_action",
        ]
    }
