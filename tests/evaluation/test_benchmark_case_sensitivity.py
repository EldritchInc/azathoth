"""Tests that benchmark cases are labelled, and datasets as sensitive as their cases (ADR 0123)."""

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.revisions import content_digest
from azathoth.sensitivity import Sensitivity

EXPECTED = ExpectedOutcome(description="Two words.", value=2, comparison=OutcomeComparison.EXACT)


def case(
    number: int,
    sensitivity: Sensitivity | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        id=UUID(int=number),
        input=f"case {number}",
        expected=EXPECTED,
        sensitivity=sensitivity,
    )


def dataset(
    *cases: BenchmarkCase,
) -> BenchmarkDataset:
    return BenchmarkDataset(
        id=UUID(int=100),
        name="claims",
        description="Claims.",
        cases=cases,
    )


# Cases


def test_a_case_is_unlabelled_by_default() -> None:
    assert case(1).sensitivity is None


@pytest.mark.parametrize("label", list(Sensitivity))
def test_a_labelled_case_dumps_its_label_and_reads_back(
    label: Sensitivity,
) -> None:
    labelled = case(1, label)

    assert labelled.model_dump(mode="json")["sensitivity"] == label.value
    assert BenchmarkCase.model_validate_json(labelled.model_dump_json()) == labelled


def test_an_unlabelled_case_dumps_as_it_did_before_labels() -> None:
    assert "sensitivity" not in case(1).model_dump(mode="json")
    assert "sensitivity" not in json.loads(case(1).model_dump_json())


def test_labels_change_no_unlabelled_datasets_digest() -> None:
    unlabelled = dataset(case(1), case(2))

    assert content_digest(unlabelled) == content_digest(
        BenchmarkDataset.model_validate_json(unlabelled.model_dump_json())
    )
    assert content_digest(unlabelled) != content_digest(
        dataset(case(1, Sensitivity.RESTRICTED), case(2))
    )


def test_an_unknown_label_is_refused() -> None:
    with pytest.raises(ValidationError):
        BenchmarkCase.model_validate(
            {
                "input": 1,
                "expected": EXPECTED.model_dump(mode="json"),
                "sensitivity": "secret",
            }
        )


# Datasets


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ((), Sensitivity.INTERNAL),
        ((None,), Sensitivity.INTERNAL),
        ((Sensitivity.PUBLIC,), Sensitivity.PUBLIC),
        ((Sensitivity.PUBLIC, Sensitivity.PUBLIC), Sensitivity.PUBLIC),
        ((Sensitivity.PUBLIC, None), Sensitivity.INTERNAL),
        ((Sensitivity.PUBLIC, Sensitivity.RESTRICTED, None), Sensitivity.RESTRICTED),
    ],
)
def test_a_dataset_is_as_sensitive_as_its_most_sensitive_case(
    labels: tuple[Sensitivity | None, ...],
    expected: Sensitivity,
) -> None:
    assert (
        dataset(*(case(number, label) for number, label in enumerate(labels, 1))).sensitivity
        is expected
    )


def test_adding_a_restricted_case_restricts_the_dataset() -> None:
    public = dataset(case(1, Sensitivity.PUBLIC))

    assert public.with_case(case(2, Sensitivity.RESTRICTED)).sensitivity is Sensitivity.RESTRICTED
    assert public.sensitivity is Sensitivity.PUBLIC


def test_a_dataset_keeps_no_label_of_its_own() -> None:
    assert "sensitivity" not in dataset(case(1, Sensitivity.RESTRICTED)).model_dump(mode="json")


# Documents


def test_a_benchmark_document_may_label_its_cases() -> None:
    labelled = dataset(case(1, Sensitivity.RESTRICTED), case(2))

    parsed = decode_benchmark_document(encode_benchmark_document(labelled))

    assert [item.sensitivity for item in parsed.cases] == [Sensitivity.RESTRICTED, None]
    assert parsed.sensitivity is Sensitivity.RESTRICTED
    assert parsed == labelled
