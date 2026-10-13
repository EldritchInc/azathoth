"""Tests for normalized-text outcome evaluation."""

import asyncio

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    ExpectedOutcome,
    NormalizedMatchEvaluator,
    OutcomeComparison,
    normalize_json_value,
    normalize_text,
)


def evaluate(
    expected: JsonValue,
    actual: JsonValue,
) -> EvaluationResult:
    """Evaluate one actual value against one normalized expectation."""

    return asyncio.run(
        NormalizedMatchEvaluator().evaluate(
            ExpectedOutcome(
                description="Normalized expectation",
                value=expected,
                comparison=OutcomeComparison.NORMALIZED,
            ),
            actual,
        )
    )


def test_normalized_comparison_is_declared() -> None:
    assert OutcomeComparison("normalized") is OutcomeComparison.NORMALIZED


@pytest.mark.parametrize(
    ("text", "normalized"),
    (
        ("Duplicate_Charge", "duplicate_charge"),
        ("  duplicate   charge \n", "duplicate charge"),
        ("\tline one\r\nline two\t", "line one line two"),
        ("ＲＥＦＵＮＤ", "refund"),
        ("ﬁle", "file"),
        ("STRASSE", "strasse"),
        ("Straße", "strasse"),
        ("", ""),
    ),
)
def test_normalize_text(
    text: str,
    normalized: str,
) -> None:
    assert normalize_text(text) == normalized


def test_normalize_json_value_preserves_structure_and_keys() -> None:
    assert normalize_json_value(
        {
            "Label": "  Refund ",
            "tags": ["A", "b"],
            "count": 2,
            "urgent": True,
            "note": None,
        }
    ) == {
        "Label": "refund",
        "tags": ["a", "b"],
        "count": 2,
        "urgent": True,
        "note": None,
    }


def test_normalized_match_passes_for_formatting_differences() -> None:
    result = evaluate(
        "duplicate_charge",
        "  Duplicate_Charge\n",
    )

    assert result.passed
    assert result.score == 1.0
    assert result.reason == "Actual value matched expected value after normalization."
    assert result.evidence == (
        EvaluationEvidence(label="expected", value="duplicate_charge"),
        EvaluationEvidence(label="actual", value="  Duplicate_Charge\n"),
        EvaluationEvidence(label="normalized_expected", value="duplicate_charge"),
        EvaluationEvidence(label="normalized_actual", value="duplicate_charge"),
    )


def test_normalized_match_passes_for_nested_formatting_differences() -> None:
    assert evaluate(
        {"intent": "refund", "tags": ["billing", "urgent"]},
        {"intent": "REFUND ", "tags": ["Billing", " urgent"]},
    ).passed


def test_normalized_match_fails_for_different_labels() -> None:
    result = evaluate(
        {"intent": "refund"},
        {"intent": "Duplicate Charge"},
    )

    assert not result.passed
    assert result.score == 0.0
    assert result.reason == (
        "Actual value did not match expected value after normalization at $.intent."
    )
    assert result.evidence[4:] == (EvaluationEvidence(label="difference_path", value="$.intent"),)


def test_normalized_match_does_not_normalize_object_keys() -> None:
    result = evaluate(
        {"intent": "refund"},
        {"Intent": "refund"},
    )

    assert not result.passed
    assert result.evidence[4:] == (EvaluationEvidence(label="difference_path", value="$"),)


def test_normalized_match_preserves_array_order() -> None:
    assert not evaluate(
        ["a", "b"],
        ["B", "A"],
    ).passed


def test_normalized_match_does_not_remove_inner_spaces() -> None:
    assert not evaluate(
        "duplicate charge",
        "duplicatecharge",
    ).passed


def test_normalized_match_rejects_boolean_for_number() -> None:
    result = evaluate(
        {"count": 1},
        {"count": True},
    )

    assert not result.passed
    assert result.evidence[4:] == (
        EvaluationEvidence(label="difference_path", value="$.count"),
        EvaluationEvidence(label="expected_type", value="number"),
        EvaluationEvidence(label="actual_type", value="boolean"),
    )


def test_normalized_match_does_not_convert_text_to_other_types() -> None:
    assert not evaluate(True, "true").passed
    assert not evaluate(1, "1").passed


def test_normalized_match_records_evaluator_identity() -> None:
    result = evaluate("x", "X")

    assert result.evaluator_name == "normalized-match"
    assert result.evaluator_version == "1.0.0"
