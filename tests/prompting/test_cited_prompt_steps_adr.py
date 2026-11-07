"""Tests that ADR 0116 quotes the real rendering and refusals of extractions in prompts."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import ExtractionHandle, Segment, SegmentedText
from azathoth.context import (
    Context,
    ContextEvent,
    LineageRun,
    LineageStep,
    StepLineage,
    running_step,
)
from azathoth.inputs import ContentRef, InMemoryContentStore, content_bytes_digest
from azathoth.prompting import (
    WORKFLOW_INPUT_BOUND_EVENT_TYPE,
    CitationCheckError,
    CitationPolicy,
    CitedSource,
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    PromptInputBinding,
    PromptOutputFormat,
    PromptTemplate,
    check_citations,
    check_native_citations,
    render_extraction,
    stored_citation_checks,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    NativeCitation,
    Prompt,
    PromptContentError,
    UnsupportedModelRequestError,
    openrouter_request,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolContentAccess, providing_tool_content

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0116-cited-prompt-steps.md"

RUN = UUID("c1620000-0000-4000-8000-000000000010")

TEXT = "Claim 0412.\nFiled by the insured.\n\nReceived on December 14."

CLAIM = SegmentedText(
    tool="segment_pdf",
    version="1.0.0",
    source_digest=content_bytes_digest(b"%PDF-1.7"),
    media_type="application/pdf",
    text=TEXT,
    segments=(
        Segment(id="p1.s1", start=0, end=33, page=1),
        Segment(id="p1.s2", start=35, end=len(TEXT), page=1),
    ),
)

DIGEST = CLAIM.digest()

HANDLE = CLAIM.handle()


def render(
    handle: ExtractionHandle = HANDLE,
    *,
    kept: frozenset[str] = frozenset({DIGEST}),
    stored: bool = True,
    give_access: bool = True,
    in_step: bool = True,
) -> str:
    """Render the claim's extraction, as a step of one run, under some conditions."""

    store = InMemoryContentStore()

    if stored:
        CLAIM.store(store)

    access = ToolContentAccess(
        store=store,
        initial_context={RUN: Context()}.get,
        kept_extractions=lambda run_id: kept,
    )
    step = StepLineage(
        step=LineageStep(workflow_id=RUN, run_id=RUN, step_id=RUN, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=RUN, run_id=RUN),
    )

    def call() -> str:
        if in_step:
            with running_step(step):
                return render_extraction("claim", handle, strategy_name="<NAME>")

        return render_extraction("claim", handle, strategy_name="<NAME>")

    if give_access:
        with providing_tool_content(access):
            return call()

    return call()


def refusal(
    attempt: Callable[[], str],
) -> str:
    """Return the message one rendering is refused with."""

    with pytest.raises(PromptContentError) as raised:
        attempt()

    return str(raised.value)


def citation_refusal(
    output: JsonValue,
    *,
    shown: str = "<SOURCE>",
) -> str:
    """Return the message checking one reply's citations against the claim is refused with."""

    with pytest.raises(CitationCheckError) as raised:
        check_citations(
            output,
            sources={shown: CitedSource(segmented=CLAIM)},
            policy=CitationPolicy(),
            store=InMemoryContentStore(),
            strategy_name="<NAME>",
        )

    return str(raised.value)


def specification_refusal() -> str:
    """Return the message a cited specification with text output is refused with."""

    with pytest.raises(ValidationError) as raised:
        ContextPromptStrategySpec.model_validate(
            {
                "metadata": {
                    "id": str(RUN),
                    "name": "<NAME>",
                    "description": "Cite.",
                    "version": "1.0.0",
                },
                "template": {"text": "Cite."},
                "model_selection": {"provider": "test", "model": "citing"},
                "citations": {},
            }
        )

    return raised.value.errors()[0]["msg"].removeprefix("Value error, ")


def storeless_refusal() -> str:
    """Return the message a cited step with no content store is refused with."""

    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(id=RUN, name="<NAME>", description="Cite.", version="1.0.0"),
        template=PromptTemplate(text="Cite."),
        language_model=DeterministicLanguageModel(response_text="{}"),
        output_format=PromptOutputFormat.JSON,
        citations=CitationPolicy(),
    )

    with pytest.raises(PromptContentError) as raised:
        asyncio.run(strategy.run(Context()))

    return str(raised.value)


def native_refusal(
    citation: NativeCitation,
    *,
    documents: tuple[str, ...] = (CLAIM.source_digest,),
) -> str:
    """Return the message checking one native citation against the claim is refused with."""

    with pytest.raises(CitationCheckError) as raised:
        check_native_citations(
            [citation],
            documents=documents,
            sources={"<SOURCE>": CitedSource(segmented=CLAIM)},
            policy=CitationPolicy(native=True),
            store=InMemoryContentStore(),
            strategy_name="<NAME>",
        )

    return str(raised.value)


def native_specification_refusal() -> str:
    """Return the message a natively cited specification with JSON output is refused with."""

    with pytest.raises(ValidationError) as raised:
        ContextPromptStrategySpec.model_validate(
            {
                "metadata": {
                    "id": str(RUN),
                    "name": "<NAME>",
                    "description": "Cite.",
                    "version": "1.0.0",
                },
                "template": {"text": "Cite."},
                "model_selection": {"provider": "test", "model": "citing"},
                "output_format": "json",
                "citations": {"native": True},
            }
        )

    return raised.value.errors()[0]["msg"].removeprefix("Value error, ")


def missing_extraction_refusal() -> str:
    """Return the message a natively cited prompt showing a PDF without its extraction gets."""

    pdf = b"%PDF-1.7"
    handle = ContentRef(
        digest=content_bytes_digest(pdf), media_type="application/pdf", size_bytes=len(pdf)
    )
    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(id=RUN, name="<NAME>", description="Cite.", version="1.0.0"),
        template=PromptTemplate(
            text="{document}",
            bindings=(PromptInputBinding(variable_name="document", input_name="document"),),
        ),
        language_model=DeterministicLanguageModel(),
        citations=CitationPolicy(native=True),
    )
    context = Context(
        events=(
            ContextEvent(
                event_type=WORKFLOW_INPUT_BOUND_EVENT_TYPE,
                payload={"name": "document", "value": handle.to_value()},
                producer="workflow-runner",
            ),
        )
    )

    with pytest.raises(PromptContentError) as raised:
        asyncio.run(strategy.run(context))

    #
    # The table names the claim's extraction as <DIGEST>; this refusal names
    # the PDF shown, so its digest stands in for the placeholder the same way.
    #
    return str(raised.value).replace(handle.digest, DIGEST)


def openrouter_refusal() -> str:
    """Return the message an OpenRouter model asked for native citations refuses with."""

    with pytest.raises(UnsupportedModelRequestError) as raised:
        openrouter_request("<MODEL>", Prompt(text="Cite.", native_citations=True))

    return str(raised.value)


def record_refusal() -> str:
    """Return the message reading back content that is not a record of checks is refused with."""

    store = InMemoryContentStore()
    digest = store.put(b"{}")

    with pytest.raises(CitationCheckError) as raised:
        stored_citation_checks(store, digest)

    return str(raised.value).replace(digest, DIGEST)


DOCUMENTED: list[tuple[str, Callable[[], str]]] = [
    (
        "Prompt strategy '<NAME>' shows extraction <DIGEST>, which this run cannot give: "
        "it has no content store.",
        lambda: refusal(lambda: render(give_access=False)),
    ),
    (
        "Prompt strategy '<NAME>' shows extraction <DIGEST>, which only a workflow step can give.",
        lambda: refusal(lambda: render(in_step=False)),
    ),
    (
        "Prompt strategy '<NAME>' shows extraction <DIGEST>, which no step of this run kept.",
        lambda: refusal(lambda: render(kept=frozenset())),
    ),
    (
        "Extraction <DIGEST> is not in the content store.",
        lambda: refusal(lambda: render(stored=False)),
    ),
    (
        "Prompt strategy '<NAME>' shows extraction <DIGEST>, but its handle does not describe "
        "the extraction the content store holds.",
        lambda: refusal(lambda: render(HANDLE.model_copy(update={"version": "2.0.0"}))),
    ),
    (
        "Prompt strategy '<NAME>' checks citations, which only a JSON reply holds; its "
        "output format is text.",
        specification_refusal,
    ),
    (
        "Prompt strategy '<NAME>' cites source '<SOURCE>', which its prompt does not show.",
        lambda: citation_refusal(
            [{"source": "<SOURCE>", "segment": "p1.s1", "quote": "x"}],
            shown="claim",
        ),
    ),
    (
        "Prompt strategy '<NAME>' cites '<QUOTE>' from segment <SEGMENT> of source "
        "'<SOURCE>', which the segment does not hold.",
        lambda: citation_refusal(
            [{"source": "<SOURCE>", "segment": "p1.s2", "quote": "<QUOTE>"}]
        ).replace("p1.s2", "<SEGMENT>"),
    ),
    (
        "Prompt strategy '<NAME>' cites segment <SEGMENT> of source '<SOURCE>', which has "
        "no such segment.",
        lambda: citation_refusal(
            [{"source": "<SOURCE>", "segment": "p9.s9", "quote": "x"}]
        ).replace("p9.s9", "<SEGMENT>"),
    ),
    (
        "Prompt strategy '<NAME>' checks citations, which this run cannot keep: it has no "
        "content store.",
        storeless_refusal,
    ),
    (
        "Prompt strategy '<NAME>' checks native citations, which its model returns beside a "
        "text reply; its output format is json.",
        native_specification_refusal,
    ),
    (
        "Prompt strategy '<NAME>' asks for native citations of content <DIGEST>, but shows no "
        "extraction of it to check them against.",
        missing_extraction_refusal,
    ),
    (
        "Prompt strategy '<NAME>' was cited by its model from document <INDEX>, which its "
        "prompt does not show.",
        lambda: native_refusal(
            NativeCitation(document=1, quote="x"),
        ).replace("document 1", "document <INDEX>"),
    ),
    (
        "Prompt strategy '<NAME>' was cited by its model quoting '<QUOTE>' from source "
        "'<SOURCE>', which no segment<WHERE> holds.",
        lambda: native_refusal(NativeCitation(document=0, quote="<QUOTE>")).replace(
            "which no segment holds", "which no segment<WHERE> holds"
        ),
    ),
    (
        "OpenRouter model '<MODEL>' cannot return native citations; cite segments in the "
        "reply instead.",
        openrouter_refusal,
    ),
    (
        "Content <DIGEST> is not a record of citation checks.",
        record_refusal,
    ),
]
"""Each refusal ADR 0116 quotes, and what produces it."""


@pytest.mark.parametrize(
    ("documented", "produce"),
    [pytest.param(*row, id=row[0][:48]) for row in DOCUMENTED],
)
def test_the_adr_quotes_the_real_refusal(
    documented: str,
    produce: Callable[[], str],
) -> None:
    assert f"\n{documented}\n" in ADR.read_text(encoding="utf-8")
    assert produce() == documented.replace("<DIGEST>", DIGEST)


def test_the_adr_shows_the_real_rendering() -> None:
    assert f"```text\n{render()}\n```" in ADR.read_text(encoding="utf-8")


def test_the_adr_quotes_no_text_the_tests_do_not_check() -> None:
    text = ADR.read_text(encoding="utf-8")
    decision = text[text.index("## Decision") : text.index("## Consequences")]
    quoted = {
        line
        for block in decision.split("```text\n")[1:]
        for line in block.split("```", 1)[0].splitlines()
    }

    assert quoted == {documented for documented, _ in DOCUMENTED} | set(render().splitlines())


def test_the_adr_is_listed_in_the_index() -> None:
    index = (ROOT / "docs" / "adrs" / "README.md").read_text(encoding="utf-8")

    assert "- [ADR 0116: Cited Prompt Steps](0116-cited-prompt-steps.md)\n" in index
