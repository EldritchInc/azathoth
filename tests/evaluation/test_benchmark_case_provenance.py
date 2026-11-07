"""Tests that a benchmark case names where its input came from (ADR 0117)."""

import warnings
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.evaluation import BenchmarkCase, ExpectedOutcome, OutcomeComparison
from azathoth.inputs import InputOrigin, InputProvenance, content_bytes_digest

CASE_ID = UUID("c1680000-0000-4000-8000-000000000001")

PDF = b"%PDF-1.7\n%%EOF\n"

EXPECTED = ExpectedOutcome(
    description="Received.", value="December 14", comparison=OutcomeComparison.EXACT
)


def handle(
    content: bytes = PDF,
    media_type: str = "application/pdf",
) -> JsonValue:
    """Return the handle of some content."""

    return {
        "content": {
            "digest": content_bytes_digest(content),
            "media_type": media_type,
            "size_bytes": len(content),
        }
    }


def provenance(
    media_type: str = "application/pdf",
    content: bytes = PDF,
) -> InputProvenance:
    """Return the provenance of a file read from S3."""

    return InputProvenance(
        uri="s3://claims/0412.pdf",
        origin=InputOrigin(uri="s3://claims/0412.pdf", version_id="3sL4kqtJlcpXroDTDmJ"),
        media_type=media_type,
        size_bytes=len(content),
        digest=content_bytes_digest(content),
    )


def test_a_case_without_provenance_serializes_as_it_always_has() -> None:
    case = BenchmarkCase(id=CASE_ID, input={"text": "x"}, expected=EXPECTED)

    assert case.model_dump(mode="json") == {
        "id": str(CASE_ID),
        "input": {"text": "x"},
        "expected": EXPECTED.model_dump(mode="json"),
        "metadata": {},
    }


def test_a_case_with_provenance_round_trips_it() -> None:
    case = BenchmarkCase(
        id=CASE_ID, input=handle(), input_provenance=provenance(), expected=EXPECTED
    )
    dumped = case.model_dump(mode="json")

    assert dumped["input_provenance"] == provenance().model_dump(mode="json")
    assert BenchmarkCase.model_validate(dumped) == case


@pytest.mark.parametrize(
    "case_input",
    [
        pytest.param({"text": "x"}, id="not-a-handle"),
        pytest.param(handle(b"%PDF-2.0"), id="other-content"),
        pytest.param(handle(media_type="image/png"), id="other-media-type"),
        pytest.param(
            {"content": {"digest": content_bytes_digest(PDF), "media_type": "application/pdf"}},
            id="not-quite-a-handle",
        ),
    ],
)
def test_a_case_whose_provenance_names_binary_content_must_give_its_handle(
    case_input: JsonValue,
) -> None:
    with pytest.raises(ValidationError) as raised:
        BenchmarkCase(
            id=CASE_ID, input=case_input, input_provenance=provenance(), expected=EXPECTED
        )

    assert raised.value.errors()[0]["msg"] == (
        f"Value error, Benchmark case {CASE_ID} names application/pdf content "
        f"{content_bytes_digest(PDF)} as its input provenance, but its input is not that "
        "content's handle."
    )


def test_a_case_whose_provenance_names_a_json_file_holds_any_value() -> None:
    case = BenchmarkCase(
        id=CASE_ID,
        input=handle(),
        input_provenance=provenance("application/json", b'{"content": 1}'),
        expected=EXPECTED,
    )

    assert case.input == handle()


def test_a_case_without_provenance_may_hold_json_shaped_like_a_handle() -> None:
    assert BenchmarkCase(id=CASE_ID, input=handle(), expected=EXPECTED).input == handle()


def test_a_case_dumps_as_python_values_without_warnings() -> None:
    case = BenchmarkCase(
        id=CASE_ID, input=handle(), input_provenance=provenance(), expected=EXPECTED
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        dumped = case.model_dump()

    assert dumped["id"] == CASE_ID
    assert BenchmarkCase.model_validate(dumped) == case
