"""Tests for appending one case to a benchmark dataset."""

from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkCaseConflictError,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.revisions import content_digest

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")
EXISTING_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")
NEW_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

INPUT: JsonValue = {
    "text": "the old ones wait",
}


def create_case(
    *,
    case_id: UUID,
    case_input: JsonValue = INPUT,
    value: JsonValue = 4,
    comparison: OutcomeComparison = OutcomeComparison.EXACT,
    description: str = "Word count",
) -> BenchmarkCase:
    """Create one deterministic benchmark case."""

    return BenchmarkCase(
        id=case_id,
        input=case_input,
        expected=ExpectedOutcome(
            description=description,
            value=value,
            comparison=comparison,
        ),
    )


def create_dataset() -> BenchmarkDataset:
    """Create one benchmark dataset with a single case."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="Word count",
        description="Count words.",
        version="2.1.0",
        cases=(
            create_case(
                case_id=EXISTING_CASE_ID,
            ),
        ),
    )


def test_with_case_appends_after_every_existing_case() -> None:
    dataset = create_dataset()

    added = create_case(
        case_id=NEW_CASE_ID,
        case_input={"text": "ph'nglui"},
        value=1,
    )

    extended = dataset.with_case(added)

    assert tuple(case.id for case in extended.cases) == (
        EXISTING_CASE_ID,
        NEW_CASE_ID,
    )
    assert extended.cases[-1] == added


def test_with_case_keeps_dataset_identity_and_declared_fields() -> None:
    dataset = create_dataset()

    extended = dataset.with_case(
        create_case(
            case_id=NEW_CASE_ID,
            value=5,
        )
    )

    assert extended.id == DATASET_ID
    assert extended.name == dataset.name
    assert extended.description == dataset.description
    assert extended.version == "2.1.0"


def test_with_case_leaves_the_original_dataset_unchanged() -> None:
    dataset = create_dataset()
    before = content_digest(dataset)

    dataset.with_case(
        create_case(
            case_id=NEW_CASE_ID,
            value=5,
        )
    )

    assert tuple(case.id for case in dataset.cases) == (EXISTING_CASE_ID,)
    assert content_digest(dataset) == before


def test_with_case_rejects_an_equivalent_case() -> None:
    dataset = create_dataset()

    with pytest.raises(BenchmarkCaseConflictError) as raised:
        dataset.with_case(
            create_case(
                case_id=NEW_CASE_ID,
                description="A different description.",
            )
        )

    assert str(raised.value) == (
        f"Benchmark dataset {DATASET_ID} already contains case {EXISTING_CASE_ID} "
        "with this input and expected outcome."
    )


def test_with_case_compares_values_as_json() -> None:
    dataset = create_dataset()

    with pytest.raises(BenchmarkCaseConflictError):
        dataset.with_case(
            create_case(
                case_id=NEW_CASE_ID,
                value=4.0,
            )
        )


def test_with_case_accepts_the_same_input_with_a_different_expected_value() -> None:
    extended = create_dataset().with_case(
        create_case(
            case_id=NEW_CASE_ID,
            value=5,
        )
    )

    assert len(extended.cases) == 2


def test_with_case_accepts_the_same_input_and_value_under_a_different_comparison() -> None:
    extended = create_dataset().with_case(
        create_case(
            case_id=NEW_CASE_ID,
            comparison=OutcomeComparison.NORMALIZED,
        )
    )

    assert len(extended.cases) == 2


def test_with_case_accepts_a_different_input_with_the_same_expected_value() -> None:
    extended = create_dataset().with_case(
        create_case(
            case_id=NEW_CASE_ID,
            case_input={"text": "that is not dead"},
        )
    )

    assert len(extended.cases) == 2


def test_with_case_does_not_treat_booleans_as_numbers() -> None:
    dataset = BenchmarkDataset(
        id=DATASET_ID,
        name="Flags",
        description="Booleans are not numbers.",
        cases=(
            create_case(
                case_id=EXISTING_CASE_ID,
                value=True,
            ),
        ),
    )

    extended = dataset.with_case(
        create_case(
            case_id=NEW_CASE_ID,
            value=1,
        )
    )

    assert len(extended.cases) == 2


def test_with_case_rejects_a_reused_case_identifier() -> None:
    with pytest.raises(ValueError) as raised:
        create_dataset().with_case(
            create_case(
                case_id=EXISTING_CASE_ID,
                value=5,
            )
        )

    assert "Benchmark dataset cannot contain duplicate case identifiers." in str(raised.value)
