"""Tests that a benchmark case's run receives its input as the case's source did (ADR 0117)."""

from uuid import UUID

from pydantic import JsonValue

from azathoth.evaluation import BenchmarkCase, ExpectedOutcome, OutcomeComparison
from azathoth.inputs import InputProvenance, content_bytes_digest
from azathoth.workflows import (
    BENCHMARK_INPUT_PRODUCER,
    WORKFLOW_INPUT_EVENT_TYPE,
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    benchmark_case_context,
)

PDF = b"%PDF-1.7\n%%EOF\n"

EXPECTED = ExpectedOutcome(
    description="Received.", value="December 14", comparison=OutcomeComparison.EXACT
)

HANDLE: JsonValue = {
    "content": {
        "digest": content_bytes_digest(PDF),
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
    }
}

PROVENANCE = InputProvenance(
    uri="file:///claims/0412.pdf",
    media_type="application/pdf",
    size_bytes=len(PDF),
    digest=content_bytes_digest(PDF),
)


def test_a_case_without_provenance_is_received_as_one_input_event() -> None:
    (event,) = benchmark_case_context(
        BenchmarkCase(id=UUID(int=1), input={"text": "x"}, expected=EXPECTED)
    ).events

    assert (event.event_type, event.payload, event.producer) == (
        WORKFLOW_INPUT_EVENT_TYPE,
        {"input": {"text": "x"}},
        BENCHMARK_INPUT_PRODUCER,
    )


def test_a_case_with_provenance_is_received_with_it_as_its_run_was() -> None:
    received, resolved = benchmark_case_context(
        BenchmarkCase(id=UUID(int=1), input=HANDLE, input_provenance=PROVENANCE, expected=EXPECTED)
    ).events

    assert (received.event_type, received.payload) == (
        WORKFLOW_INPUT_EVENT_TYPE,
        {"input": HANDLE},
    )
    assert (resolved.event_type, resolved.payload, resolved.producer) == (
        WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
        PROVENANCE.model_dump(mode="json"),
        BENCHMARK_INPUT_PRODUCER,
    )
    assert resolved.occurred_at == received.occurred_at


def test_the_benchmark_input_producer_is_named() -> None:
    assert BENCHMARK_INPUT_PRODUCER == "azathoth.benchmark"
