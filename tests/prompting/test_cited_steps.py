"""Tests that a cited prompt step's citations are checked, replaced and kept (ADR 0116)."""

import asyncio
import json
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import Segment, SegmentedText
from azathoth.context import (
    Context,
    LineageRun,
    LineageStep,
    WorkflowLineage,
    create_lineage_event,
)
from azathoth.inputs import (
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
    PromptInputBinding,
    PromptOutputFormat,
    PromptTemplate,
    check_citations,
    generate_context_prompt_candidates,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelResponse,
    Prompt,
    PromptContentError,
)
from azathoth.strategies import StrategyMetadata, StrategyOutcome, StrategyResourceBinding
from azathoth.tools import (
    EXTRACTION_RESOURCE_KIND,
    ToolContentAccess,
    providing_tool_content,
    received_origin,
)
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
    create_workflow_input_events,
    journaled_extractions,
    journaled_initial_context,
)
from tests.model_authorization import portfolio_for_catalog

WORKFLOW_ID = UUID("c1630000-0000-4000-8000-000000000001")

SEGMENT_STEP = UUID("c1630000-0000-4000-8000-000000000002")

CITED_STEP = UUID("c1630000-0000-4000-8000-000000000003")

STRATEGY_ID = UUID("c1630000-0000-4000-8000-000000000004")

PDF = b"%PDF-1.7\n%%EOF\n"

TEXT = "Claim 0412.\nFiled by the insured.\n\nReceived on December 14."

CLAIM = SegmentedText(
    tool="segment_pdf",
    version="1.0.0",
    source_digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    text=TEXT,
    segments=(
        Segment(id="p1.s1", start=0, end=33, page=1),
        Segment(id="p1.s2", start=35, end=len(TEXT), page=1),
    ),
)

ORIGIN = InputOrigin(uri="s3://claims/0412.pdf", version_id="3sL4kqtJlcpXroDTDmJ")


def citation(
    segment: str = "p1.s2",
    quote: str = "December 14",
    source: str = "claim",
) -> dict[str, JsonValue]:
    """Return one citation as a reply holds it."""

    return {"source": source, "segment": segment, "quote": quote}


def checked(
    output: JsonValue,
    *,
    policy: CitationPolicy | None = None,
    origin: InputOrigin | None = None,
) -> tuple[Any, StrategyResourceBinding, InMemoryContentStore]:
    """Check a reply's citations against the claim; return it, the record and the store."""

    store = InMemoryContentStore()
    replaced, record = check_citations(
        output,
        sources={"claim": CitedSource(segmented=CLAIM, origin=origin)},
        policy=policy if policy is not None else CitationPolicy(),
        store=store,
        strategy_name="answer",
    )

    return replaced, record, store


def refused(
    output: JsonValue,
    *,
    policy: CitationPolicy | None = None,
) -> str:
    """Return the message checking a reply's citations is refused with."""

    with pytest.raises(CitationCheckError) as raised:
        checked(output, policy=policy)

    return str(raised.value)


def test_a_verified_citation_is_replaced_by_its_check_and_anchor() -> None:
    replaced, _, _ = checked({"answer": "December 14", "citations": [citation()]})
    (check,) = replaced["citations"]
    anchor = check.pop("anchor")

    assert check == {
        "source": "claim",
        "segment": "p1.s2",
        "quote": "December 14",
        "status": "verified",
    }
    assert anchor["digest"] == CLAIM.source_digest
    assert anchor["extraction"] == CLAIM.extraction().model_dump(mode="json")
    assert [selector["type"] for selector in anchor["selectors"]] == [
        "TextQuoteSelector",
        "TextPositionSelector",
        "FragmentSelector",
    ]
    assert anchor["selectors"][2]["conformsTo"] == "http://tools.ietf.org/rfc/rfc3778"
    assert replaced["answer"] == "December 14"


def test_an_anchor_names_the_sources_origin() -> None:
    replaced, _, _ = checked([citation()], origin=ORIGIN)

    assert replaced[0]["anchor"]["origin"] == ORIGIN.model_dump(mode="json")


def test_citations_are_found_anywhere_in_a_reply_and_checked_in_order() -> None:
    reply: JsonValue = {
        "claims": [
            {"text": "Claim 0412.", "support": [citation("p1.s1", "Claim 0412")]},
            {"text": "Received.", "support": [citation(), citation("p1.s1", "insured")]},
        ],
        "summary": citation(),
    }
    replaced, record, store = checked(reply)

    assert replaced["claims"][0]["text"] == "Claim 0412."
    assert [check["quote"] for check in replaced["claims"][1]["support"]] == [
        "December 14",
        "insured",
    ]
    assert replaced["summary"]["status"] == "verified"
    assert record.attributes["citations"] == 4

    stored = store.get(record.identifier)

    assert stored is not None
    assert [check["quote"] for check in json.loads(stored)["checks"]] == [
        "Claim 0412",
        "December 14",
        "insured",
        "December 14",
    ]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({**citation(), "page": 1}, id="more-keys"),
        pytest.param({"source": "claim", "segment": "p1.s2"}, id="fewer-keys"),
        pytest.param({**citation(), "quote": 14}, id="quote-not-a-string"),
        pytest.param({**citation(), "segment": None}, id="segment-not-a-string"),
    ],
)
def test_an_object_that_is_not_exactly_a_citation_is_left_as_it_is(
    value: JsonValue,
) -> None:
    replaced, record, _ = checked({"evidence": value})

    assert replaced == {"evidence": value}
    assert record.attributes["citations"] == 0


def test_the_record_is_the_checks_as_canonical_json_named_by_their_digest() -> None:
    replaced, record, store = checked([citation()])
    stored = store.get(record.identifier)

    assert stored == json.dumps(
        {"checks": replaced},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert record.identifier == content_bytes_digest(stored)
    assert record.kind == CITATIONS_RESOURCE_KIND == "citations"


def test_the_record_counts_each_status() -> None:
    _, record, _ = checked(
        [
            citation(),
            citation(quote="December  14"),
            citation(quote="March 3"),
            citation(segment="p9.s9"),
        ],
        policy=CitationPolicy(on_unverified="keep"),
    )

    assert record.attributes == {
        "citations": 4,
        "verified": 1,
        "verified_normalized": 1,
        "quote_not_found": 1,
        "unknown_segment": 1,
    }


def test_a_reply_that_cites_nothing_records_no_checks() -> None:
    replaced, record, store = checked({"answer": "No idea."})

    assert replaced == {"answer": "No idea."}
    assert store.get(record.identifier) == b'{"checks":[]}'
    assert record.attributes["citations"] == 0


def test_a_quote_found_once_normalized_is_verified_under_fail() -> None:
    replaced, _, _ = checked([citation(quote="Received  on\nDecember 14")])

    assert replaced[0]["status"] == "verified_normalized"


def test_a_quote_the_segment_does_not_hold_fails_the_reply() -> None:
    assert refused([citation(quote="March 3")]) == (
        "Prompt strategy 'answer' cites 'March 3' from segment p1.s2 of source 'claim', "
        "which the segment does not hold."
    )


def test_a_segment_the_source_does_not_have_fails_the_reply() -> None:
    assert refused([citation(segment="p9.s9")]) == (
        "Prompt strategy 'answer' cites segment p9.s9 of source 'claim', which has no such segment."
    )


def test_the_first_unverified_citation_is_the_one_named() -> None:
    message = refused([citation(), citation(quote="March 3"), citation(segment="p9.s9")])

    assert "'March 3'" in message


def test_under_keep_unverified_citations_are_kept_without_anchors() -> None:
    replaced, _, _ = checked(
        [citation(quote="March 3"), citation(segment="p9.s9")],
        policy=CitationPolicy(on_unverified="keep"),
    )

    assert [(check["status"], "anchor" in check) for check in replaced] == [
        ("quote_not_found", False),
        ("unknown_segment", False),
    ]


@pytest.mark.parametrize("on_unverified", ["fail", "keep"])
def test_a_source_the_prompt_did_not_show_always_fails_the_reply(
    on_unverified: str,
) -> None:
    policy = CitationPolicy.model_validate({"on_unverified": on_unverified})

    assert refused([citation(source="invoice")], policy=policy) == (
        "Prompt strategy 'answer' cites source 'invoice', which its prompt does not show."
    )


def test_a_policy_fails_unverified_citations_by_default() -> None:
    assert CitationPolicy().on_unverified == "fail"
    assert CitationPolicy().model_dump(mode="json") == {"on_unverified": "fail"}


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"on_unverified": "ignore"}, id="unknown-policy"),
        pytest.param({"on_unverified": "fail", "strict": True}, id="extra-key"),
    ],
)
def test_a_policy_is_validated(
    value: dict[str, JsonValue],
) -> None:
    with pytest.raises(ValidationError):
        CitationPolicy.model_validate(value)


def specification(
    **fields: Any,
) -> ContextPromptStrategySpec:
    """Return a context prompt specification of the cited step, with some fields."""

    return ContextPromptStrategySpec.model_validate(
        {
            "metadata": {
                "id": str(STRATEGY_ID),
                "name": "answer",
                "description": "Answer with citations.",
                "version": "1.0.0",
            },
            "template": {
                "text": "{claim}",
                "bindings": [{"variable_name": "claim", "input_name": "claim"}],
            },
            "model_selection": {"provider": "test", "model": "citing"},
            **fields,
        }
    )


def test_a_cited_step_replies_in_json() -> None:
    with pytest.raises(ValidationError) as raised:
        specification(citations={})

    assert (
        "Prompt strategy 'answer' checks citations, which only a JSON reply holds; its "
        "output format is text."
    ) in str(raised.value)


def test_a_cited_specification_serializes_its_policy() -> None:
    cited = specification(output_format="json", citations={"on_unverified": "keep"})

    assert cited.model_dump(mode="json")["citations"] == {"on_unverified": "keep"}
    assert ContextPromptStrategySpec.model_validate(cited.model_dump(mode="json")) == cited


def test_a_specification_without_citations_serializes_as_it_always_did() -> None:
    assert "citations" not in specification(output_format="json").model_dump(mode="json")
    assert "citations" not in specification().model_dump(mode="json")


def test_a_candidate_carries_its_specifications_policy() -> None:
    catalog = ModelCatalog(
        models=(ModelMetadata(provider="test", model="citing", display_name="Citing"),)
    )
    (candidate,) = generate_context_prompt_candidates(
        specification(output_format="json", citations={"on_unverified": "keep"}),
        catalog,
        LanguageModelRegistry(models={"test/citing": CitingModel([])}),
        portfolio=portfolio_for_catalog(catalog),
    )

    assert candidate.citations == CitationPolicy(on_unverified="keep")


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


class CitingModel:
    """A language model that answers with each of some replies in turn."""

    def __init__(
        self,
        replies: list[JsonValue],
    ) -> None:
        self._replies = list(replies)
        self.prompts: list[Prompt] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt and answer with the next reply."""

        self.prompts.append(prompt)

        return ModelResponse(
            text=json.dumps(self._replies.pop(0)),
            provider="test",
            model="citing",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )


def received_claim() -> Context:
    """Return an initial context that received the claim's PDF from its origin."""

    return Context(
        events=create_workflow_input_events(
            ResolvedInput(
                value={
                    "content": {
                        "digest": CLAIM.source_digest,
                        "media_type": "application/pdf",
                        "size_bytes": len(PDF),
                    }
                },
                media_type="application/pdf",
                provenance=InputProvenance(
                    inline=True,
                    origin=ORIGIN,
                    media_type="application/pdf",
                    size_bytes=len(PDF),
                    digest=CLAIM.source_digest,
                ),
            ),
            producer="azathoth.cli",
        )
    )


def run_cited(
    model: CitingModel,
    *,
    policy: CitationPolicy | None = None,
    attempts: int = 1,
    content: bool = True,
) -> Any:
    """Run a workflow that keeps the claim's extraction, then a cited step that reads it."""

    journal = InMemoryRunJournalRepository()
    store = InMemoryContentStore()
    workflow = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Answer from a claim",
            description="Keep an extraction of a claim, then answer from it with citations.",
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
                        description="Answer when the claim was received, with citations.",
                        version="1.0.0",
                    ),
                    template=PromptTemplate(
                        text="{claim}\n\nWhen was it received? Cite the segment.",
                        bindings=(PromptInputBinding(variable_name="claim", input_name="claim"),),
                    ),
                    language_model=model,
                    output_format=PromptOutputFormat.JSON,
                    citations=policy if policy is not None else CitationPolicy(),
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
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=attempts,
                    initial_delay_seconds=0.0,
                ),
            ),
        ),
    )
    access = ToolContentAccess(
        store=store,
        initial_context=lambda run_id: journaled_initial_context(journal, run_id),
        kept_extractions=lambda run_id: journaled_extractions(journal, run_id),
    )
    runner = WorkflowRunner(journal=journal, content=access if content else None)
    result = asyncio.run(runner.run_recording_failures(workflow, received_claim()))

    return result, store


def test_a_cited_step_outputs_its_checked_citations_and_records_them() -> None:
    model = CitingModel([{"received": "December 14", "citations": [citation()]}])
    result, store = run_cited(model)
    cited = result.steps[1]

    assert cited.status is WorkflowStepStatus.EXECUTED

    (check,) = cited.execution.output["citations"]

    assert (check["status"], check["anchor"]["origin"]) == (
        "verified",
        ORIGIN.model_dump(mode="json"),
    )

    (record,) = (
        resource
        for resource in cited.execution.resources
        if resource.kind == CITATIONS_RESOURCE_KIND
    )
    stored = store.get(record.identifier)

    assert stored is not None
    assert json.loads(stored) == {"checks": [check]}


def test_an_unverified_citation_fails_the_attempt_and_the_step_asks_again() -> None:
    model = CitingModel(
        [
            {"received": "March 3", "citations": [citation(quote="March 3")]},
            {"received": "December 14", "citations": [citation()]},
        ]
    )
    result, _ = run_cited(model, attempts=2)
    cited = result.steps[1]

    assert cited.status is WorkflowStepStatus.EXECUTED
    assert len(model.prompts) == 2
    assert cited.attempts[0].failure.message == (
        "Prompt strategy 'answer' cites 'March 3' from segment p1.s2 of source 'claim', "
        "which the segment does not hold."
    )
    assert cited.execution.output["citations"][0]["status"] == "verified"


def test_under_keep_an_unverified_citation_is_kept_and_the_step_goes_on() -> None:
    model = CitingModel([{"received": "March 3", "citations": [citation(quote="March 3")]}])
    result, _ = run_cited(model, policy=CitationPolicy(on_unverified="keep"))
    cited = result.steps[1]

    assert cited.status is WorkflowStepStatus.EXECUTED
    assert cited.execution.output["citations"][0]["status"] == "quote_not_found"


def test_a_cited_step_without_a_content_store_cannot_keep_its_checks() -> None:
    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="answer",
            description="Answer.",
            version="1.0.0",
        ),
        template=PromptTemplate(text="When was it received?"),
        language_model=CitingModel([{"received": "December 14", "citations": []}]),
        output_format=PromptOutputFormat.JSON,
        citations=CitationPolicy(),
    )

    with pytest.raises(PromptContentError) as raised:
        asyncio.run(strategy.run(Context()))

    assert str(raised.value) == (
        "Prompt strategy 'answer' checks citations, which this run cannot keep: "
        "it has no content store."
    )


def test_a_cited_step_outside_a_run_cannot_keep_its_checks_even_with_a_store() -> None:
    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="answer",
            description="Answer.",
            version="1.0.0",
        ),
        template=PromptTemplate(text="When was it received?"),
        language_model=CitingModel([{"received": "December 14", "citations": []}]),
        output_format=PromptOutputFormat.JSON,
        citations=CitationPolicy(),
    )
    store = InMemoryContentStore()

    with (
        providing_tool_content(ToolContentAccess(store=store, initial_context=lambda run_id: None)),
        pytest.raises(PromptContentError) as raised,
    ):
        asyncio.run(strategy.run(Context()))

    assert "checks citations, which this run cannot keep" in str(raised.value)
    assert store.get(content_bytes_digest(b'{"checks":[]}')) is None


def provenance_context(
    provenance: InputProvenance,
) -> Context:
    """Return an initial context that received the PDF with one provenance."""

    return Context(
        events=create_workflow_input_events(
            ResolvedInput(
                value={
                    "content": {
                        "digest": CLAIM.source_digest,
                        "media_type": "application/pdf",
                        "size_bytes": len(PDF),
                    }
                },
                media_type="application/pdf",
                provenance=provenance,
            ),
            producer="azathoth.cli",
        )
    )


def origin_of(
    *contexts: Context,
    digest: str = CLAIM.source_digest,
) -> InputOrigin | None:
    """Return the origin of some content as a run whose lineage is these contexts sees it."""

    runs = [UUID(int=index + 1) for index in range(len(contexts))]
    known: dict[UUID, Context] = {}

    for index, context in enumerate(contexts):
        if index + 1 < len(contexts):
            context = Context(
                events=(
                    *context.events,
                    create_lineage_event(
                        WorkflowLineage(
                            depth=1,
                            parent=LineageStep(
                                workflow_id=WORKFLOW_ID,
                                run_id=runs[index + 1],
                                step_id=SEGMENT_STEP,
                                attempt=1,
                            ),
                            root=LineageRun(workflow_id=WORKFLOW_ID, run_id=runs[-1]),
                        )
                    ),
                )
            )

        known[runs[index]] = context

    return received_origin(digest, runs[0], initial_context=known.get)


def test_an_inline_inputs_origin_is_the_one_it_named() -> None:
    assert origin_of(received_claim()) == ORIGIN


def test_a_references_origin_is_the_uri_it_was_read_from() -> None:
    reference = provenance_context(
        InputProvenance(
            uri="s3://claims/0412.pdf",
            media_type="application/pdf",
            size_bytes=len(PDF),
            digest=CLAIM.source_digest,
        )
    )

    assert origin_of(reference) == InputOrigin(uri="s3://claims/0412.pdf")


def test_the_nearest_run_that_received_the_content_names_its_origin() -> None:
    reference = provenance_context(
        InputProvenance(
            uri="s3://claims/copy.pdf",
            media_type="application/pdf",
            size_bytes=len(PDF),
            digest=CLAIM.source_digest,
        )
    )

    assert origin_of(Context(), received_claim(), reference) == ORIGIN


def test_content_received_without_an_origin_or_never_received_has_none() -> None:
    inline = provenance_context(
        InputProvenance(
            inline=True,
            media_type="application/pdf",
            size_bytes=len(PDF),
            digest=CLAIM.source_digest,
        )
    )

    assert origin_of(inline) is None
    assert origin_of(received_claim(), digest="0" * 64) is None
