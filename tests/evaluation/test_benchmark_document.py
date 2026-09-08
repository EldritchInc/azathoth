"""Tests for portable benchmark dataset documents."""

import json
from uuid import UUID

import pytest

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkDocumentError,
    ExpectedOutcome,
    OutcomeComparison,
    decode_benchmark_document,
    encode_benchmark_document,
)

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_dataset() -> BenchmarkDataset:
    """Create one portable benchmark dataset."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="classification benchmark",
        description="Verify deterministic classification behavior.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=FIRST_CASE_ID,
                input={
                    "text": "This was excellent.",
                },
                expected=ExpectedOutcome(
                    description="Classify the input as positive.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "positive",
                },
            ),
            BenchmarkCase(
                id=SECOND_CASE_ID,
                input={
                    "text": "This was terrible.",
                },
                expected=ExpectedOutcome(
                    description="Classify the input as negative.",
                    value="negative",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "negative",
                },
            ),
        ),
    )


def test_encode_benchmark_document_produces_readable_json() -> None:
    encoded = encode_benchmark_document(
        create_dataset(),
    )

    payload = json.loads(encoded)

    assert payload["id"] == str(BENCHMARK_ID)
    assert payload["name"] == "classification benchmark"
    assert payload["version"] == "1.0.0"

    assert payload["cases"][0]["id"] == str(FIRST_CASE_ID)
    assert payload["cases"][1]["id"] == str(SECOND_CASE_ID)

    assert encoded.startswith("{\n")
    assert '\n  "cases": [' in encoded


def test_benchmark_document_round_trips_complete_dataset() -> None:
    original = create_dataset()

    restored = decode_benchmark_document(encode_benchmark_document(original))

    assert restored == original
    assert restored is not original


def test_benchmark_document_preserves_case_order() -> None:
    restored = decode_benchmark_document(
        encode_benchmark_document(
            create_dataset(),
        )
    )

    assert tuple(case.id for case in restored.cases) == (
        FIRST_CASE_ID,
        SECOND_CASE_ID,
    )


def test_benchmark_document_preserves_expected_outcomes() -> None:
    restored = decode_benchmark_document(
        encode_benchmark_document(
            create_dataset(),
        )
    )

    first = restored.cases[0]

    assert first.expected.description == ("Classify the input as positive.")

    assert first.expected.value == "positive"

    assert first.expected.comparison is OutcomeComparison.EXACT


def test_decode_benchmark_document_rejects_malformed_json() -> None:
    with pytest.raises(
        BenchmarkDocumentError,
        match=("Benchmark document is not a valid BenchmarkDataset"),
    ):
        decode_benchmark_document("{this is definitely not json")


def test_decode_benchmark_document_rejects_wrong_document_shape() -> None:
    with pytest.raises(
        BenchmarkDocumentError,
        match=("Benchmark document is not a valid BenchmarkDataset"),
    ):
        decode_benchmark_document('{"hello":"eldritch"}')


def test_decode_benchmark_document_rejects_invalid_domain_data() -> None:
    dataset = create_dataset().model_dump(
        mode="json",
    )

    dataset["name"] = ""

    with pytest.raises(
        BenchmarkDocumentError,
        match=("Benchmark document is not a valid BenchmarkDataset"),
    ):
        decode_benchmark_document(json.dumps(dataset))


def test_decode_benchmark_document_rejects_duplicate_case_ids() -> None:
    dataset = create_dataset().model_dump(
        mode="json",
    )

    dataset["cases"][1]["id"] = str(FIRST_CASE_ID)

    with pytest.raises(
        BenchmarkDocumentError,
        match=("Benchmark document is not a valid BenchmarkDataset"),
    ):
        decode_benchmark_document(json.dumps(dataset))


def test_benchmark_document_error_preserves_validation_cause() -> None:
    try:
        decode_benchmark_document('{"invalid":true}')
    except BenchmarkDocumentError as exc:
        assert exc.__cause__ is not None
    else:
        raise AssertionError("Expected invalid benchmark document to fail.")
