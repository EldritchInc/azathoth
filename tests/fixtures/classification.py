"""Reusable classification benchmark fixtures."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationExample:
    """One labeled classification example."""

    text: str
    expected: str


CLASSIFICATION_EXAMPLES = (
    ClassificationExample(
        text="I absolutely loved this movie.",
        expected="positive",
    ),
    ClassificationExample(
        text="This was fantastic and exceeded my expectations.",
        expected="positive",
    ),
    ClassificationExample(
        text="The experience was excellent.",
        expected="positive",
    ),
    ClassificationExample(
        text="Everything about this was terrible.",
        expected="negative",
    ),
    ClassificationExample(
        text="I regret buying this product.",
        expected="negative",
    ),
    ClassificationExample(
        text="This was a complete waste of time.",
        expected="negative",
    ),
    ClassificationExample(
        text="The food was okay.",
        expected="neutral",
    ),
    ClassificationExample(
        text="Nothing particularly stood out.",
        expected="neutral",
    ),
    ClassificationExample(
        text="It worked as expected.",
        expected="neutral",
    ),
)
