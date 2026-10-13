"""Deterministic evaluator comparing normalized text within JSON values."""

import unicodedata

from pydantic import JsonValue

from azathoth.evaluation.json_equality import first_json_difference
from azathoth.evaluation.models import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
)
from azathoth.evaluation.protocols import EvaluatorMetadata


def normalize_text(
    text: str,
) -> str:
    """Return text with compatibility forms, case, and whitespace normalized.

    Text is NFKC-normalized, case-folded, normalized again so case folding
    cannot reintroduce non-canonical forms, and stripped with internal
    whitespace runs collapsed to single spaces.
    """

    folded = unicodedata.normalize(
        "NFKC",
        unicodedata.normalize("NFKC", text).casefold(),
    )

    return " ".join(folded.split())


def normalize_json_value(
    value: JsonValue,
) -> JsonValue:
    """Return one JSON value with every string value normalized.

    Object keys, array order, numbers, booleans, and null are preserved.
    """

    if isinstance(value, str):
        return normalize_text(value)

    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]

    if isinstance(value, dict):
        return {key: normalize_json_value(item) for key, item in value.items()}

    return value


class NormalizedMatchEvaluator:
    """Evaluate outputs using type-strict equality after text normalization."""

    def __init__(self) -> None:
        self._metadata = EvaluatorMetadata(
            name="normalized-match",
            description=(
                "Compare expected and actual values using type-strict JSON equality "
                "after Unicode, case, and whitespace normalization of string values."
            ),
            version="1.0.0",
        )

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        """Compare normalized forms of two JSON values.

        Only string values are normalized. Object keys and array order must
        still match, and booleans still never equal numbers.
        """

        normalized_expected = normalize_json_value(expected.value)
        normalized_actual = normalize_json_value(actual)

        difference = first_json_difference(
            normalized_expected,
            normalized_actual,
        )

        evidence = [
            EvaluationEvidence(
                label="expected",
                value=expected.value,
            ),
            EvaluationEvidence(
                label="actual",
                value=actual,
            ),
            EvaluationEvidence(
                label="normalized_expected",
                value=normalized_expected,
            ),
            EvaluationEvidence(
                label="normalized_actual",
                value=normalized_actual,
            ),
        ]

        if difference is None:
            return EvaluationResult(
                evaluator_name=self.metadata.name,
                evaluator_version=self.metadata.version,
                score=1.0,
                threshold=1.0,
                status=EvaluationStatus.PASSED,
                reason="Actual value matched expected value after normalization.",
                evidence=tuple(evidence),
            )

        evidence.append(
            EvaluationEvidence(
                label="difference_path",
                value=difference.path,
            )
        )

        if difference.expected_type != difference.actual_type:
            evidence.extend(
                (
                    EvaluationEvidence(
                        label="expected_type",
                        value=difference.expected_type,
                    ),
                    EvaluationEvidence(
                        label="actual_type",
                        value=difference.actual_type,
                    ),
                )
            )

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            evaluator_version=self.metadata.version,
            score=0.0,
            threshold=1.0,
            status=EvaluationStatus.FAILED,
            reason=(
                "Actual value did not match expected value after normalization "
                f"at {difference.path}."
            ),
            evidence=tuple(evidence),
        )
