"""Tests that a kept citations record is read back as the checks it holds (ADR 0116)."""

import pytest

from azathoth.citations import Segment, SegmentedText
from azathoth.inputs import InMemoryContentStore, content_bytes_digest
from azathoth.prompting import (
    CitationCheckError,
    CitationPolicy,
    CitedSource,
    check_citations,
    stored_citation_checks,
)

TEXT = "Claim 0412.\n\nReceived on December 14."

CLAIM = SegmentedText(
    tool="segment_pdf",
    version="1.0.0",
    source_digest=content_bytes_digest(b"%PDF-1.7"),
    media_type="application/pdf",
    text=TEXT,
    segments=(
        Segment(id="p1.s1", start=0, end=11, page=1),
        Segment(id="p1.s2", start=13, end=len(TEXT), page=1),
    ),
)


def test_a_kept_record_reads_back_as_the_checks_it_holds_in_order() -> None:
    store = InMemoryContentStore()
    output, record = check_citations(
        [
            {"source": "claim", "segment": "p1.s2", "quote": "December 14"},
            {"source": "claim", "segment": "p1.s1", "quote": "Denied."},
        ],
        sources={"claim": CitedSource(segmented=CLAIM)},
        policy=CitationPolicy(on_unverified="keep"),
        store=store,
        strategy_name="answer",
    )

    assert stored_citation_checks(store, record.identifier) == tuple(
        output if isinstance(output, list) else ()
    )


def test_a_record_the_store_does_not_hold_is_none() -> None:
    assert stored_citation_checks(InMemoryContentStore(), "c" * 64) is None


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"\xff", id="not-utf8"),
        pytest.param(b"{", id="not-json"),
        pytest.param(b"[]", id="not-an-object"),
        pytest.param(b'{"checks": [], "more": 1}', id="another-key"),
        pytest.param(b'{"checks": {}}', id="checks-not-a-list"),
        pytest.param(b'{"checks": [1]}', id="a-check-not-an-object"),
    ],
)
def test_content_that_is_not_a_record_of_checks_is_refused(
    content: bytes,
) -> None:
    store = InMemoryContentStore()
    digest = store.put(content)

    with pytest.raises(CitationCheckError) as raised:
        stored_citation_checks(store, digest)

    assert str(raised.value) == f"Content {digest} is not a record of citation checks."
