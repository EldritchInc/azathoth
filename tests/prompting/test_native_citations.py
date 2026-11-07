"""Tests that a provider's own citations are checked as a cited step's are (ADR 0116)."""

import asyncio
import json
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.citations import Segment, SegmentedText
from azathoth.context import Context
from azathoth.inputs import (
    ContentRef,
    InMemoryContentStore,
    InputOrigin,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.prompting import (
    CITATIONS_RESOURCE_KIND,
    CitationCheckError,
    CitationPolicy,
    CitedSource,
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    PromptBinding,
    PromptInputBinding,
    PromptTemplate,
    check_native_citations,
)
from azathoth.providers import ModelResponse, NativeCitation, Prompt, PromptContentError
from azathoth.strategies import StrategyMetadata, StrategyOutcome, StrategyResourceBinding
from azathoth.tools import EXTRACTION_RESOURCE_KIND, ToolContentAccess
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
    create_workflow_input_events,
    journaled_extractions,
    journaled_initial_context,
)

WORKFLOW_ID = UUID("c1640000-0000-4000-8000-000000000001")

SEGMENT_STEP = UUID("c1640000-0000-4000-8000-000000000002")

CITED_STEP = UUID("c1640000-0000-4000-8000-000000000003")

STRATEGY_ID = UUID("c1640000-0000-4000-8000-000000000004")

PDF = b"%PDF-1.7\n%%EOF\n"

OTHER_PDF = b"%PDF-1.7\n% another\n%%EOF\n"

TEXT = "Claim 0412.\n\nFiled by the insured.\n\nReceived on December 14."

CLAIM = SegmentedText(
    tool="segment_pdf",
    version="1.0.0",
    source_digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    text=TEXT,
    segments=(
        Segment(id="p1.s1", start=0, end=11, page=1),
        Segment(id="p2.s1", start=13, end=34, page=2),
        Segment(id="p3.s1", start=36, end=len(TEXT), page=3),
    ),
)

ORIGIN = InputOrigin(uri="s3://claims/0412.pdf", version_id="3sL4kqtJlcpXroDTDmJ")

DOCUMENT = ContentRef(
    digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    size_bytes=len(PDF),
)


def native(
    quote: str = "Received on December 14.",
    pages: tuple[int, int] | None = (3, 3),
    document: int = 0,
) -> NativeCitation:
    """Return one citation a provider might return of the claim."""

    return NativeCitation(
        document=document,
        quote=quote,
        pages=pages,
        supports="on December 14",
    )


def checked(
    *citations: NativeCitation,
    policy: CitationPolicy | None = None,
) -> tuple[list[dict[str, Any]], StrategyResourceBinding, InMemoryContentStore]:
    """Check some native citations against the claim; return the checks, record and store."""

    store = InMemoryContentStore()
    checks, record = check_native_citations(
        citations,
        documents=[CLAIM.source_digest],
        sources={"claim": CitedSource(segmented=CLAIM, origin=ORIGIN)},
        policy=policy if policy is not None else CitationPolicy(native=True),
        store=store,
        strategy_name="answer",
    )

    return checks, record, store


def refused(
    *citations: NativeCitation,
) -> str:
    """Return the message checking some native citations is refused with."""

    with pytest.raises(CitationCheckError) as raised:
        checked(*citations)

    return str(raised.value)


def test_a_native_citation_is_checked_among_the_segments_on_its_pages() -> None:
    (check,), _, _ = checked(native())
    anchor = check.pop("anchor")

    assert check == {
        "source": "claim",
        "segment": "p3.s1",
        "quote": "Received on December 14.",
        "status": "verified",
        "supports": "on December 14",
        "pages": [3, 3],
    }
    assert anchor["origin"] == ORIGIN.model_dump(mode="json")
    assert anchor["extraction"] == CLAIM.extraction().model_dump(mode="json")


def test_a_quote_on_another_page_than_the_one_cited_is_not_verified() -> None:
    assert refused(native(quote="Filed by the insured.", pages=(3, 3))) == (
        "Prompt strategy 'answer' was cited by its model quoting 'Filed by the insured.' from "
        "source 'claim', which no segment on page 3 holds."
    )


def test_a_range_of_pages_includes_both_ends() -> None:
    checks, _, _ = checked(
        native(quote="Claim 0412.", pages=(1, 2)),
        native(quote="Filed by the insured.", pages=(1, 2)),
    )

    assert [check["segment"] for check in checks] == ["p1.s1", "p2.s1"]


def test_a_quote_on_a_page_after_the_range_is_not_verified() -> None:
    assert refused(native(pages=(1, 2))) == (
        "Prompt strategy 'answer' was cited by its model quoting 'Received on December 14.' "
        "from source 'claim', which no segment on pages 1 to 2 holds."
    )


def test_the_first_segment_holding_the_quote_verifies_it() -> None:
    (check,), _, _ = checked(native(quote="ed", pages=None))

    assert check["segment"] == "p2.s1"


def test_a_range_read_backwards_is_from_its_first_page_on() -> None:
    (check,), _, _ = checked(native(quote="Filed by the insured.", pages=(2, 1)))

    assert (check["segment"], check["pages"]) == ("p2.s1", [2, 2])


def test_a_citation_naming_no_pages_is_checked_against_every_segment() -> None:
    (check,), _, _ = checked(native(quote="Filed by the insured.", pages=None))

    assert check["segment"] == "p2.s1"
    assert "pages" not in check


def test_a_quote_found_once_normalized_is_verified() -> None:
    (check,), _, _ = checked(native(quote="Received  on\nDecember 14."))

    assert check["status"] == "verified_normalized"


@pytest.mark.parametrize(
    ("pages", "where"),
    [
        pytest.param((1, 2), " on pages 1 to 2", id="range"),
        pytest.param(None, "", id="no-pages"),
    ],
)
def test_a_quote_no_segment_holds_fails_naming_where_it_was_looked_for(
    pages: tuple[int, int] | None,
    where: str,
) -> None:
    assert refused(native(quote="March 3.", pages=pages)) == (
        f"Prompt strategy 'answer' was cited by its model quoting 'March 3.' from source "
        f"'claim', which no segment{where} holds."
    )


def test_under_keep_an_unverified_native_citation_is_kept_with_no_segment() -> None:
    (check,), record, _ = checked(
        native(quote="March 3."),
        policy=CitationPolicy(native=True, on_unverified="keep"),
    )

    assert (check["segment"], check["status"], "anchor" in check) == (
        None,
        "quote_not_found",
        False,
    )
    assert record.attributes["quote_not_found"] == 1


def test_a_citation_of_a_document_the_prompt_did_not_show_always_fails() -> None:
    assert refused(native(document=1)) == (
        "Prompt strategy 'answer' was cited by its model from document 1, which its prompt "
        "does not show."
    )


def test_a_citation_of_a_document_with_no_extraction_shown_fails() -> None:
    other = content_bytes_digest(OTHER_PDF)

    with pytest.raises(CitationCheckError) as raised:
        check_native_citations(
            [native()],
            documents=[other],
            sources={"claim": CitedSource(segmented=CLAIM)},
            policy=CitationPolicy(native=True),
            store=InMemoryContentStore(),
            strategy_name="answer",
        )

    assert str(raised.value) == (
        f"Prompt strategy 'answer' was cited by its model from content {other}, which its "
        "prompt shows no extraction of."
    )


def test_the_native_checks_are_recorded_as_a_replys_are() -> None:
    checks, record, store = checked(native(), native(quote="Claim 0412.", pages=(1, 1)))
    stored = store.get(record.identifier)

    assert stored is not None
    assert json.loads(stored) == {"checks": checks}
    assert record.kind == CITATIONS_RESOURCE_KIND
    assert record.attributes["verified"] == 2


def specification(
    **fields: Any,
) -> ContextPromptStrategySpec:
    """Return a context prompt specification of the cited step, with some fields."""

    return ContextPromptStrategySpec.model_validate(
        {
            "metadata": {
                "id": str(STRATEGY_ID),
                "name": "answer",
                "description": "Answer with the provider's citations.",
                "version": "1.0.0",
            },
            "template": {"text": "When was the claim received?"},
            "model_selection": {"provider": "bedrock", "model": "claude"},
            **fields,
        }
    )


def test_a_natively_cited_step_replies_in_text() -> None:
    with pytest.raises(ValidationError) as raised:
        specification(output_format="json", citations={"native": True})

    assert (
        "Prompt strategy 'answer' checks native citations, which its model returns beside a "
        "text reply; its output format is json."
    ) in str(raised.value)


def test_a_natively_cited_specification_serializes_its_policy() -> None:
    cited = specification(citations={"native": True})

    assert cited.model_dump(mode="json")["citations"] == {
        "on_unverified": "fail",
        "native": True,
    }
    assert "native" not in CitationPolicy().model_dump(mode="json")


class KeepingStrategy:
    """A strategy that keeps the claim's extraction as the engine keeps a tool's (ADR 0114)."""

    def __init__(
        self,
        store: InMemoryContentStore,
    ) -> None:
        self._store = store

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return StrategyMetadata(
            id=SEGMENT_STEP,
            name="segment",
            description="Keep an extraction of the claim.",
            version="1.0.0",
        )

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Keep the claim's extraction; output its handle and record keeping it."""

        digest = CLAIM.store(self._store)

        return StrategyOutcome(
            output={"extraction": CLAIM.handle().to_value()},
            resources=(StrategyResourceBinding(kind=EXTRACTION_RESOURCE_KIND, identifier=digest),),
        )


class NativelyCitingModel:
    """A language model that answers in text with its own citations of the document."""

    def __init__(
        self,
        citations: tuple[NativeCitation, ...],
    ) -> None:
        self._citations = citations
        self.prompts: list[Prompt] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt, and answer with the citations."""

        self.prompts.append(prompt)

        return ModelResponse(
            text="It was received on December 14.",
            provider="test",
            model="citing",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            latency_ms=0,
            estimated_cost_usd=0.0,
            citations=self._citations,
        )


def received_claim() -> Context:
    """Return an initial context that received the claim's PDF from its origin."""

    return Context(
        events=create_workflow_input_events(
            ResolvedInput(
                value=DOCUMENT.to_value(),
                media_type="application/pdf",
                provenance=InputProvenance(
                    inline=True,
                    origin=ORIGIN,
                    media_type="application/pdf",
                    size_bytes=len(PDF),
                    digest=DOCUMENT.digest,
                ),
            ),
            producer="azathoth.cli",
        )
    )


def run_natively_cited(
    model: NativelyCitingModel,
    *,
    show_extraction: bool = True,
) -> Any:
    """Run a workflow that keeps the claim's extraction, then a step shown both PDF and it."""

    journal = InMemoryRunJournalRepository()
    store = InMemoryContentStore()
    store.put(PDF)
    text = "{document}\n\n{claim}\n\nWhen was it received?" if show_extraction else "{document}"
    bindings: tuple[PromptBinding | PromptInputBinding, ...] = (
        PromptBinding(
            variable_name="document",
            event_type="workflow.input.received",
            field_name="input",
        ),
        *(
            (PromptInputBinding(variable_name="claim", input_name="claim"),)
            if show_extraction
            else ()
        ),
    )
    workflow = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Answer from a claim",
            description="Keep an extraction of a claim, then answer from the claim itself.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=SEGMENT_STEP,
                strategy=KeepingStrategy(store),
                outputs=(WorkflowValueBinding(name="extraction", path=("extraction",)),),
            ),
            WorkflowCandidateStep(
                id=CITED_STEP,
                strategy=ContextPromptStrategy(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="answer",
                        description="Answer when the claim was received.",
                        version="1.0.0",
                    ),
                    template=PromptTemplate(text=text, bindings=bindings),
                    language_model=model,
                    citations=CitationPolicy(native=True),
                ),
                depends_on=(SEGMENT_STEP,),
                inputs=(
                    WorkflowInputBinding(
                        name="claim",
                        source=WorkflowValueReference(
                            producer_step_id=SEGMENT_STEP,
                            name="extraction",
                        ),
                    ),
                ),
                outputs=(WorkflowValueBinding(name="answer"),),
            ),
        ),
    )
    runner = WorkflowRunner(
        journal=journal,
        content=ToolContentAccess(
            store=store,
            initial_context=lambda run_id: journaled_initial_context(journal, run_id),
            kept_extractions=lambda run_id: journaled_extractions(journal, run_id),
        ),
    )

    return asyncio.run(runner.run_recording_failures(workflow, received_claim())), store


def test_a_natively_cited_step_outputs_its_text_and_checked_citations() -> None:
    model = NativelyCitingModel((native(),))
    result, store = run_natively_cited(model)
    cited = result.steps[1]

    assert cited.status is WorkflowStepStatus.EXECUTED
    assert model.prompts[0].native_citations is True
    assert model.prompts[0].contents() == (DOCUMENT,)

    output = cited.execution.output

    assert output["text"] == "It was received on December 14."
    assert [(check["segment"], check["status"]) for check in output["citations"]] == [
        ("p3.s1", "verified")
    ]

    (record,) = (
        resource
        for resource in cited.execution.resources
        if resource.kind == CITATIONS_RESOURCE_KIND
    )
    stored = store.get(record.identifier)

    assert stored is not None
    assert json.loads(stored) == {"checks": output["citations"]}


def test_a_natively_cited_step_whose_quote_is_not_there_fails() -> None:
    model = NativelyCitingModel((native(quote="March 3."),))
    result, _ = run_natively_cited(model)

    assert result.steps[1].status is WorkflowStepStatus.FAILED


def test_a_document_shown_without_its_extraction_is_refused_before_the_model_is_called() -> None:
    model = NativelyCitingModel(())
    result, _ = run_natively_cited(model, show_extraction=False)
    recorded = json.dumps(result.model_dump(mode="json"))

    assert result.steps[1].status is WorkflowStepStatus.FAILED
    assert model.prompts == []
    assert (
        f"Prompt strategy 'answer' asks for native citations of content {DOCUMENT.digest}, "
        "but shows no extraction of it to check them against."
    ) in recorded


def test_a_natively_cited_step_outside_a_run_cannot_keep_its_checks() -> None:
    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="answer",
            description="Answer.",
            version="1.0.0",
        ),
        template=PromptTemplate(text="When was it received?"),
        language_model=NativelyCitingModel(()),
        citations=CitationPolicy(native=True),
    )

    with pytest.raises(PromptContentError) as raised:
        asyncio.run(strategy.run(Context()))

    assert "checks citations, which this run cannot keep" in str(raised.value)
