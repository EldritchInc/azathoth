"""Tests for reusable classification benchmark fixtures."""

from tests.fixtures.classification import (
    CLASSIFICATION_EXAMPLES,
)


def test_classification_examples_are_present() -> None:
    assert len(CLASSIFICATION_EXAMPLES) >= 9


def test_classification_labels_are_valid() -> None:
    valid = {
        "positive",
        "negative",
        "neutral",
    }

    for example in CLASSIFICATION_EXAMPLES:
        assert example.expected in valid


def test_classification_text_is_not_empty() -> None:
    for example in CLASSIFICATION_EXAMPLES:
        assert example.text.strip()
