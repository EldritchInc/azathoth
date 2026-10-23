"""Tests for the semantic judge rotation."""

import pytest
from pydantic import ValidationError

from azathoth.evaluation import (
    ExpectedOutcome,
    JudgeEntry,
    JudgeRotation,
    OutcomeComparison,
    expectation_hash,
)

ALPHA = JudgeEntry(
    provider="openrouter",
    model="alpha",
)

BETA = JudgeEntry(
    provider="openrouter",
    model="beta",
)

GAMMA = JudgeEntry(
    provider="openrouter",
    model="gamma",
)


def create_expected(
    value: str,
) -> ExpectedOutcome:
    """Create one semantic expectation."""

    return ExpectedOutcome(
        description="d",
        value=value,
        comparison=OutcomeComparison.SEMANTIC,
    )


def create_rotation() -> JudgeRotation:
    """Create a three-judge rotation."""

    return JudgeRotation(
        entries=(
            ALPHA,
            BETA,
            GAMMA,
        ),
    )


def test_judge_entry_has_provider_qualified_identifier() -> None:
    assert ALPHA.identifier == "openrouter/alpha"


def test_judge_rotation_preserves_order() -> None:
    assert create_rotation().identifiers == (
        "openrouter/alpha",
        "openrouter/beta",
        "openrouter/gamma",
    )


def test_judge_rotation_rejects_duplicate_judges() -> None:
    with pytest.raises(
        ValidationError,
        match="Judge rotation cannot contain duplicate model identifiers.",
    ):
        JudgeRotation(
            entries=(
                ALPHA,
                ALPHA,
            ),
        )


def test_judge_rotation_finds_judge_by_identifier() -> None:
    rotation = create_rotation()

    assert rotation.get("openrouter/beta") == BETA
    assert rotation.get("openrouter/missing") is None


def test_expectation_hash_is_pinned() -> None:
    """Changing the hash would silently reassign every case to new judges."""

    assert expectation_hash(create_expected("yes")) == 13718023895912765875
    assert expectation_hash(create_expected("neutral")) == 13211778983351839107


def test_expectation_hash_ignores_object_key_order() -> None:
    first = ExpectedOutcome(
        description="d",
        value={
            "a": 1,
            "b": 2,
        },
        comparison=OutcomeComparison.SEMANTIC,
    )

    second = ExpectedOutcome(
        description="d",
        value={
            "b": 2,
            "a": 1,
        },
        comparison=OutcomeComparison.SEMANTIC,
    )

    assert expectation_hash(first) == expectation_hash(second)


def test_expectation_hash_covers_description_and_comparison() -> None:
    base = create_expected("yes")

    assert expectation_hash(base) != expectation_hash(
        base.model_copy(
            update={
                "description": "other",
            },
        )
    )
    assert expectation_hash(base) != expectation_hash(
        base.model_copy(
            update={
                "comparison": OutcomeComparison.EXACT,
            },
        )
    )


def test_judges_for_starts_at_the_hashed_judge_and_wraps() -> None:
    rotation = create_rotation()

    assert rotation.judges_for(create_expected("neutral")) == (ALPHA, BETA, GAMMA)
    assert rotation.judges_for(create_expected("yes")) == (BETA, GAMMA, ALPHA)
    assert rotation.judges_for(create_expected("success")) == (GAMMA, ALPHA, BETA)


def test_judges_for_is_stable_for_the_same_expectation() -> None:
    expected = create_expected("yes")

    assert create_rotation().judges_for(expected) == create_rotation().judges_for(expected)


def test_judges_for_returns_every_judge_exactly_once() -> None:
    rotation = create_rotation()

    for value in ("neutral", "yes", "success", "failure", "refund", "no"):
        judges = rotation.judges_for(create_expected(value))

        assert sorted(judge.identifier for judge in judges) == sorted(rotation.identifiers)


def test_single_judge_rotation_always_returns_that_judge() -> None:
    rotation = JudgeRotation(
        entries=(GAMMA,),
    )

    for value in ("neutral", "yes", "success"):
        assert rotation.judges_for(create_expected(value)) == (GAMMA,)


def test_judges_for_rejects_empty_rotation() -> None:
    with pytest.raises(
        ValueError,
        match="^Judge rotation is empty.$",
    ):
        JudgeRotation().judges_for(create_expected("yes"))


def test_judge_rotation_round_trips_through_json() -> None:
    rotation = create_rotation()

    assert JudgeRotation.model_validate_json(rotation.model_dump_json()) == rotation
