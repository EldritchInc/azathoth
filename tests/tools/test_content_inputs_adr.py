"""Tests that ADR 0114 and the tools README quote content inputs' real refusals."""

import asyncio
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.inputs import (
    InMemoryContentStore,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    ContentInputError,
    ExtractionOutputError,
    ToolContentAccess,
    ToolImplementation,
    content_input_files,
    keep_extraction,
)
from azathoth.workflows import create_workflow_input_events

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0114-read-documents-with-tools.md"

TOOLS_README = ROOT / "src" / "azathoth" / "tools" / "README.md"

RUN_ID = UUID("c1400000-0000-4000-8000-000000000001")

PDF = b"%PDF-1.7\n%%EOF\n"

DIGEST = content_bytes_digest(PDF)


def quoted(
    path: Path,
    message: str,
) -> bool:
    """Return whether a document quotes one message, its digest written <SHA-256>."""

    shown = message.replace(DIGEST, "<SHA-256>")

    return f"```text\n{shown}\n```" in path.read_text(encoding="utf-8")


def refusal(
    handle: JsonValue,
    *,
    received: bool = True,
    store: InMemoryContentStore | None = None,
    access: bool = True,
) -> str:
    """Return the refusal of one handle given to a tool named segment_pdf."""

    initial = Context(
        events=tuple(
            create_workflow_input_events(
                ResolvedInput(
                    value=None,
                    media_type="application/pdf",
                    provenance=InputProvenance(
                        uri="file:///claims/claim-0412.pdf",
                        media_type="application/pdf",
                        size_bytes=len(PDF),
                        digest=DIGEST,
                    ),
                ),
                producer="azathoth.cli",
            )
        )
        if received
        else ()
    )

    if store is None:
        store = InMemoryContentStore()
        store.put(PDF)

    async def give() -> None:
        async with content_input_files(
            ToolImplementation(
                tool_id=UUID("c1400000-0000-4000-8000-000000000002"),
                tool_version="1.0.0",
                runtime=PROCESS_TOOL_RUNTIME,
                source="print('{}')\n",
                command=(sys.executable,),
                content_inputs=("document",),
            ),
            {"document": handle},
            tool="segment_pdf",
            access=ToolContentAccess(store=store, initial_context=lambda run_id: initial)
            if access
            else None,
            run_id=RUN_ID,
        ):
            pass

    with pytest.raises(ContentInputError) as raised:
        asyncio.run(give())

    return str(raised.value)


def handle(
    media_type: str = "application/pdf",
) -> JsonValue:
    """Return a handle of the test PDF."""

    return {"content": {"digest": DIGEST, "media_type": media_type, "size_bytes": len(PDF)}}


def test_the_adr_and_readme_quote_the_refusal_of_content_never_received() -> None:
    message = refusal(handle(), received=False)

    assert quoted(ADR, message)
    assert quoted(TOOLS_README, message)


def test_the_adr_quotes_the_refusal_of_relabelled_content() -> None:
    assert quoted(ADR, refusal(handle("image/png")))


def test_the_adr_quotes_the_refusal_of_content_not_matching_its_digest() -> None:
    class Tampered(InMemoryContentStore):
        """A store whose content was changed under its digest."""

        def get(self, digest: str) -> bytes | None:
            return b"%PDF-1.7 tampered"

    assert quoted(ADR, refusal(handle(), store=Tampered()))


def test_the_adr_quotes_the_refusal_of_a_run_without_content_access() -> None:
    assert quoted(ADR, refusal(handle(), access=False))


def test_the_adr_and_readme_show_the_file_a_tool_is_given() -> None:
    for path in (ADR, TOOLS_README):
        text = path.read_text(encoding="utf-8")

        assert '"content_inputs": ["document"]' in text
        assert '"path": "/tmp/azathoth-content-.../document.pdf"' in text


def extraction_refusal(
    source_digest: str,
    *,
    tool: str = "segment_pdf",
) -> str:
    """Return the refusal of an extraction a tool named segment_pdf returned."""

    document: JsonValue = {
        "path": "/tmp/document.pdf",
        "digest": DIGEST,
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
    }

    with pytest.raises(ExtractionOutputError) as raised:
        keep_extraction(
            ToolImplementation(
                tool_id=UUID("c1400000-0000-4000-8000-000000000002"),
                tool_version="1.0.0",
                runtime=PROCESS_TOOL_RUNTIME,
                source="print('{}')\n",
                command=(sys.executable,),
                content_inputs=("document",),
                extraction_output="extraction",
            ),
            {
                "extraction": {
                    "tool": tool,
                    "version": "1",
                    "source_digest": source_digest,
                    "media_type": "application/pdf",
                    "text": "Claim 0412.",
                    "segments": [{"id": "p1.s1", "start": 0, "end": 11, "page": 1}],
                }
            },
            tool="segment_pdf",
            given={"document": document},
            store=InMemoryContentStore(),
        )

    return str(raised.value)


def test_the_adr_and_readme_quote_the_refusal_of_an_extraction_of_other_content() -> None:
    other = content_bytes_digest(b"another document")
    message = extraction_refusal(other).replace(other, DIGEST)

    assert quoted(ADR, message)
    assert quoted(TOOLS_README, message)


def test_the_adr_quotes_the_refusal_of_an_extraction_naming_another_tool() -> None:
    assert quoted(ADR, extraction_refusal(DIGEST, tool="segment_text"))


def test_the_adr_and_readme_show_an_extraction_handle_as_it_is_written() -> None:
    for path in (ADR, TOOLS_README):
        text = path.read_text(encoding="utf-8")

        assert '"extraction_output": "extraction"' in text
        assert (
            '{"extraction": {"tool": "segment_pdf", "version": "1", "digest": '
            '"<SHA-256 of the extraction>", "source_digest": "<SHA-256 of the PDF>", '
            '"media_type": "application/pdf"}}'
        ) in text
