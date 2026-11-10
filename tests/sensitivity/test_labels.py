"""Tests for sensitivity labels and how they combine (ADR 0123)."""

import pytest

from azathoth.sensitivity import (
    DEFAULT_SENSITIVITY,
    Sensitivity,
    SensitivityError,
    effective_sensitivity,
    most_sensitive,
    require_no_lower,
    stored_sensitivity,
)


def test_the_labels_are_public_internal_and_restricted() -> None:
    assert [label.value for label in Sensitivity] == ["public", "internal", "restricted"]


def test_unlabelled_data_is_internal() -> None:
    assert DEFAULT_SENSITIVITY is Sensitivity.INTERNAL
    assert effective_sensitivity(None) is Sensitivity.INTERNAL


def test_a_label_is_its_own_effective_label() -> None:
    for label in Sensitivity:
        assert effective_sensitivity(label) is label


def test_labels_rank_from_public_to_restricted() -> None:
    assert [label.rank for label in Sensitivity] == [0, 1, 2]


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ((Sensitivity.PUBLIC, Sensitivity.INTERNAL), Sensitivity.INTERNAL),
        ((Sensitivity.INTERNAL, Sensitivity.PUBLIC), Sensitivity.INTERNAL),
        (
            (Sensitivity.PUBLIC, Sensitivity.RESTRICTED, Sensitivity.INTERNAL),
            Sensitivity.RESTRICTED,
        ),
        ((Sensitivity.PUBLIC, Sensitivity.PUBLIC), Sensitivity.PUBLIC),
        ((Sensitivity.PUBLIC, None), Sensitivity.INTERNAL),
        ((None, Sensitivity.RESTRICTED), Sensitivity.RESTRICTED),
        ((None,), Sensitivity.INTERNAL),
        ((), Sensitivity.INTERNAL),
    ],
)
def test_the_most_sensitive_label_wins_and_unlabelled_counts_as_internal(
    labels: tuple[Sensitivity | None, ...],
    expected: Sensitivity,
) -> None:
    assert most_sensitive(labels) is expected


def test_labels_are_never_ordered_by_their_names() -> None:
    assert sorted(label.value for label in Sensitivity) == ["internal", "public", "restricted"]
    assert most_sensitive((Sensitivity.INTERNAL, Sensitivity.PUBLIC)) is Sensitivity.INTERNAL


def test_most_sensitive_reads_any_iterable() -> None:
    assert most_sensitive(iter((Sensitivity.PUBLIC, Sensitivity.RESTRICTED))) is (
        Sensitivity.RESTRICTED
    )


@pytest.mark.parametrize(
    ("label", "floor"),
    [
        (Sensitivity.RESTRICTED, Sensitivity.RESTRICTED),
        (Sensitivity.RESTRICTED, Sensitivity.INTERNAL),
        (Sensitivity.INTERNAL, Sensitivity.INTERNAL),
        (Sensitivity.INTERNAL, Sensitivity.PUBLIC),
        (Sensitivity.PUBLIC, Sensitivity.PUBLIC),
        (None, Sensitivity.INTERNAL),
        (None, Sensitivity.PUBLIC),
    ],
)
def test_a_derived_label_may_match_or_exceed_its_source(
    label: Sensitivity | None,
    floor: Sensitivity,
) -> None:
    require_no_lower(label, floor, source="Run 1", derived="a case made from it")


@pytest.mark.parametrize(
    ("label", "floor", "message"),
    [
        (
            Sensitivity.INTERNAL,
            Sensitivity.RESTRICTED,
            "Run 1 is restricted; a case made from it cannot be internal.",
        ),
        (
            Sensitivity.PUBLIC,
            Sensitivity.INTERNAL,
            "Run 1 is internal; a case made from it cannot be public.",
        ),
        (
            None,
            Sensitivity.RESTRICTED,
            "Run 1 is restricted; a case made from it cannot be internal.",
        ),
    ],
)
def test_a_derived_label_lower_than_its_source_is_refused(
    label: Sensitivity | None,
    floor: Sensitivity,
    message: str,
) -> None:
    with pytest.raises(SensitivityError) as caught:
        require_no_lower(label, floor, source="Run 1", derived="a case made from it")

    assert str(caught.value) == message


def test_a_sensitivity_error_is_a_value_error() -> None:
    assert issubclass(SensitivityError, ValueError)


def test_an_internal_label_is_stored_as_none() -> None:
    assert stored_sensitivity(Sensitivity.INTERNAL) is None
    assert stored_sensitivity(Sensitivity.PUBLIC) is Sensitivity.PUBLIC
    assert stored_sensitivity(Sensitivity.RESTRICTED) is Sensitivity.RESTRICTED
