"""Tests that the checks a run's cited steps kept render one line each (ADR 0116)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from azathoth.cli.rendering import (
    RecordedCitations,
    render_citation_lines,
    render_production_invocation,
)
from azathoth.context import Context
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
)

STEP_ID = UUID("c1660000-0000-4000-8000-000000000001")

OTHER_STEP_ID = UUID("c1660000-0000-4000-8000-000000000002")

RECORD = "a" * 64

OTHER_RECORD = "b" * 64


def check(
    status: str = "verified",
    segment: str | None = "p1.s2",
    quote: str = "December 14",
    **more: Any,
) -> dict[str, Any]:
    """Return one kept check of a citation of the claim."""

    return {"source": "claim", "segment": segment, "quote": quote, "status": status, **more}


def test_a_run_with_no_cited_step_renders_no_lines() -> None:
    assert render_citation_lines([]) == []


def test_each_step_names_its_record_and_each_check_its_status_source_segment_and_quote() -> None:
    assert render_citation_lines(
        [
            RecordedCitations(
                step_id=STEP_ID,
                record=RECORD,
                checks=(check(), check("quote_not_found", "p2.s1", "Denied.")),
            ),
            RecordedCitations(step_id=OTHER_STEP_ID, record=OTHER_RECORD, checks=(check(),)),
        ]
    ) == [
        "Citations:",
        f"Step {STEP_ID}: 2 citations, record {RECORD}",
        "  verified claim p1.s2 'December 14'",
        "  quote_not_found claim p2.s1 'Denied.'",
        f"Step {OTHER_STEP_ID}: 1 citation, record {OTHER_RECORD}",
        "  verified claim p1.s2 'December 14'",
    ]


def test_a_step_that_checked_no_citations_says_so() -> None:
    assert render_citation_lines(
        [RecordedCitations(step_id=STEP_ID, record=RECORD, checks=())]
    ) == ["Citations:", f"Step {STEP_ID}: 0 citations, record {RECORD}"]


def test_a_providers_citation_names_its_pages_and_no_segment_when_none_verified_it() -> None:
    (_, _, *lines) = render_citation_lines(
        [
            RecordedCitations(
                step_id=STEP_ID,
                record=RECORD,
                checks=(
                    check(pages=[3, 3], supports="on December 14"),
                    check("quote_not_found", None, "March 3.", pages=[1, 2]),
                ),
            )
        ]
    )

    assert lines == [
        "  verified claim p1.s2 'December 14' on page 3",
        "  quote_not_found claim - 'March 3.' on pages 1 to 2",
    ]


def test_a_record_the_content_store_does_not_hold_is_named() -> None:
    assert render_citation_lines(
        [RecordedCitations(step_id=STEP_ID, record=RECORD, checks=None)]
    ) == ["Citations:", f"Step {STEP_ID}: record {RECORD} is not in the content store."]


def test_an_invocations_citations_come_last_even_after_a_failure() -> None:
    rendered = render_production_invocation(
        ProductionInvocation(
            id=UUID("c1660000-0000-4000-8000-000000000003"),
            workflow_id=UUID("c1660000-0000-4000-8000-000000000004"),
            created_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
            initial_context=Context(),
        ),
        result=ProductionInvocationFailure(
            invocation_id=UUID("c1660000-0000-4000-8000-000000000003"),
            error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
            message="Workflow failed.",
        ),
        run_id=None,
        citations=[RecordedCitations(step_id=STEP_ID, record=RECORD, checks=(check(),))],
    )

    assert rendered.endswith(
        "Message: Workflow failed.\n"
        "Citations:\n"
        f"Step {STEP_ID}: 1 citation, record {RECORD}\n"
        "  verified claim p1.s2 'December 14'"
    )
