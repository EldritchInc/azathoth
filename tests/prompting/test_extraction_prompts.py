"""Tests that a prompt renders the segments of an extraction its run kept (ADR 0116)."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.citations import ExtractionHandle, Segment, SegmentedText
from azathoth.context import (
    Context,
    ContextEvent,
    LineageRun,
    LineageStep,
    StepLineage,
    WorkflowLineage,
    create_lineage_event,
    running_step,
)
from azathoth.inputs import ContentStore, InMemoryContentStore, content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import (
    ContextPromptStrategy,
    PromptInputBinding,
    PromptTemplate,
    render_extraction,
)
from azathoth.providers import ModelResponse, Prompt, PromptContentError
from azathoth.strategies import StrategyMetadata, StrategyOutcome, StrategyResourceBinding
from azathoth.tools import EXTRACTION_RESOURCE_KIND, ToolContentAccess, providing_tool_content
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    RunJournalRepository,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
    journaled_extractions,
    journaled_initial_context,
)

WORKFLOW_ID = UUID("c1610000-0000-4000-8000-000000000001")

SEGMENT_STEP = UUID("c1610000-0000-4000-8000-000000000002")

PROMPT_STEP = UUID("c1610000-0000-4000-8000-000000000003")

ROOT_RUN = UUID("c1610000-0000-4000-8000-000000000010")

CHILD_RUN = UUID("c1610000-0000-4000-8000-000000000011")

OTHER_RUN = UUID("c1610000-0000-4000-8000-000000000012")

BOUND_EVENT_TYPE = "workflow.input.bound"

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

RENDERED_CLAIM = (
    '<source name="claim">\n'
    "[p1.s1] Claim 0412.\nFiled by the insured.\n\n"
    "[p1.s2] Received on December 14.\n"
    "</source>"
)

EMPTY = SegmentedText(
    tool="segment_pdf",
    version="1.0.0",
    source_digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    text="",
)


def lineage_context(
    parent: UUID | None = None,
) -> Context:
    """Return a run's initial context, naming its parent run when it has one."""

    if parent is None:
        return Context()

    return Context(
        events=(
            create_lineage_event(
                WorkflowLineage(
                    depth=1,
                    parent=LineageStep(
                        workflow_id=WORKFLOW_ID,
                        run_id=parent,
                        step_id=SEGMENT_STEP,
                        attempt=1,
                    ),
                    root=LineageRun(workflow_id=WORKFLOW_ID, run_id=ROOT_RUN),
                )
            ),
        )
    )


def access(
    kept: dict[UUID, frozenset[str]],
    *,
    stored: tuple[SegmentedText, ...] = (CLAIM, EMPTY),
    runs: dict[UUID, Context] | None = None,
) -> ToolContentAccess:
    """Return content access whose runs kept some extractions, over a store holding some."""

    store = InMemoryContentStore()

    for extraction in stored:
        extraction.store(store)

    known = runs if runs is not None else {ROOT_RUN: lineage_context()}

    return ToolContentAccess(
        store=store,
        initial_context=known.get,
        kept_extractions=lambda run_id: kept.get(run_id, frozenset()),
    )


def step(
    run_id: UUID = ROOT_RUN,
) -> StepLineage:
    """Return the lineage of a step of one run."""

    return StepLineage(
        step=LineageStep(workflow_id=WORKFLOW_ID, run_id=run_id, step_id=PROMPT_STEP, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=WORKFLOW_ID, run_id=ROOT_RUN),
    )


def rendered(
    handle: ExtractionHandle,
    *,
    content: ToolContentAccess | None,
    run_id: UUID | None = ROOT_RUN,
    variable: str = "claim",
) -> str:
    """Render one extraction as a running step of one run would."""

    def in_step() -> str:
        if run_id is None:
            return render_extraction(variable, handle, strategy_name="describe_claim")

        with running_step(step(run_id)):
            return render_extraction(variable, handle, strategy_name="describe_claim")

    if content is None:
        return in_step()

    with providing_tool_content(content):
        return in_step()


KEPT = {ROOT_RUN: frozenset({CLAIM.digest(), EMPTY.digest()})}


def test_an_extraction_renders_its_segments_by_id_inside_its_source() -> None:
    assert rendered(CLAIM.handle(), content=access(KEPT)) == RENDERED_CLAIM


def test_the_source_is_named_by_the_variable() -> None:
    assert rendered(CLAIM.handle(), content=access(KEPT), variable="form").startswith(
        '<source name="form">\n[p1.s1] '
    )


def test_an_extraction_with_no_segments_renders_an_empty_source() -> None:
    assert rendered(EMPTY.handle(), content=access(KEPT)) == '<source name="claim">\n</source>'


def test_a_child_renders_an_extraction_its_parent_kept() -> None:
    runs = {ROOT_RUN: lineage_context(), CHILD_RUN: lineage_context(parent=ROOT_RUN)}

    assert (
        rendered(CLAIM.handle(), content=access(KEPT, runs=runs), run_id=CHILD_RUN)
        == RENDERED_CLAIM
    )


Refused = Callable[[], str]


@pytest.mark.parametrize(
    ("attempt", "message"),
    [
        pytest.param(
            lambda: rendered(CLAIM.handle(), content=None),
            f"Prompt strategy 'describe_claim' shows extraction {CLAIM.digest()}, which this "
            "run cannot give: it has no content store.",
            id="no-access",
        ),
        pytest.param(
            lambda: rendered(CLAIM.handle(), content=access(KEPT), run_id=None),
            f"Prompt strategy 'describe_claim' shows extraction {CLAIM.digest()}, which only "
            "a workflow step can give.",
            id="no-step",
        ),
        pytest.param(
            lambda: rendered(CLAIM.handle(), content=access({})),
            f"Prompt strategy 'describe_claim' shows extraction {CLAIM.digest()}, which no "
            "step of this run kept.",
            id="never-kept",
        ),
        pytest.param(
            lambda: rendered(
                CLAIM.handle(),
                content=access(
                    {OTHER_RUN: frozenset({CLAIM.digest()})},
                    runs={ROOT_RUN: lineage_context(), OTHER_RUN: lineage_context()},
                ),
            ),
            f"Prompt strategy 'describe_claim' shows extraction {CLAIM.digest()}, which no "
            "step of this run kept.",
            id="another-run-kept-it",
        ),
        pytest.param(
            lambda: rendered(CLAIM.handle(), content=access(KEPT, stored=())),
            f"Extraction {CLAIM.digest()} is not in the content store.",
            id="not-in-store",
        ),
        pytest.param(
            lambda: rendered(
                CLAIM.handle().model_copy(update={"tool": "segment_text"}),
                content=access(KEPT),
            ),
            f"Prompt strategy 'describe_claim' shows extraction {CLAIM.digest()}, but its "
            "handle does not describe the extraction the content store holds.",
            id="handle-mismatch",
        ),
    ],
)
def test_an_extraction_a_prompt_cannot_render_is_refused(
    attempt: Refused,
    message: str,
) -> None:
    with pytest.raises(PromptContentError) as raised:
        attempt()

    assert str(raised.value) == message


def test_content_that_is_not_a_segmented_text_is_refused() -> None:
    store = InMemoryContentStore()
    digest = store.put(b"not json")
    handle = CLAIM.handle().model_copy(update={"digest": digest})
    content = ToolContentAccess(
        store=store,
        initial_context={ROOT_RUN: lineage_context()}.get,
        kept_extractions=lambda run_id: frozenset({digest}),
    )

    with pytest.raises(PromptContentError) as raised:
        rendered(handle, content=content)

    assert str(raised.value) == (f"Content {digest} is not a segmented text: it is not UTF-8 JSON.")


def bound(
    **values: JsonValue,
) -> Context:
    """Return a step context with some bound inputs."""

    return Context(
        events=tuple(
            ContextEvent(
                event_type=BOUND_EVENT_TYPE,
                payload={"name": name, "value": value},
                producer="workflow-runner",
            )
            for name, value in values.items()
        )
    )


def template_render(
    text: str,
    *,
    strategy_name: str | None = None,
    **values: JsonValue,
) -> Prompt:
    """Render a template binding each value by its name, in a step of the root run."""

    template = PromptTemplate(
        text=text,
        bindings=tuple(PromptInputBinding(variable_name=name, input_name=name) for name in values),
    )

    with providing_tool_content(access(KEPT)), running_step(step()):
        return template.render(bound(**values), strategy_name=strategy_name)


def test_a_template_renders_a_bound_extraction_beside_its_text() -> None:
    prompt = template_render(
        "Read the claim.\n\n{claim}\n\nWhen was it received?",
        claim=CLAIM.handle().to_value(),
    )

    assert prompt == Prompt(text=f"Read the claim.\n\n{RENDERED_CLAIM}\n\nWhen was it received?")


def test_an_extraction_handle_inside_another_value_stays_json() -> None:
    value: JsonValue = [CLAIM.handle().to_value()]
    prompt = template_render("{claim}", claim=value)

    assert prompt == Prompt(text=json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def test_a_templates_refusal_names_its_strategy_or_none() -> None:
    template = PromptTemplate(
        text="{claim}",
        bindings=(PromptInputBinding(variable_name="claim", input_name="claim"),),
    )

    with pytest.raises(PromptContentError) as raised:
        template.render(bound(claim=CLAIM.handle().to_value()))

    assert str(raised.value).startswith(f"A prompt shows extraction {CLAIM.digest()}, ")


class KeepingStrategy:
    """A strategy that keeps an extraction as the engine keeps a tool's (ADR 0114)."""

    def __init__(
        self,
        store: ContentStore,
        *,
        record: bool = True,
        kind: str = EXTRACTION_RESOURCE_KIND,
    ) -> None:
        self._store = store
        self._record = record
        self._kind = kind

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
        """Keep the claim's extraction; output its handle and record it, or not."""

        digest = CLAIM.store(self._store)

        return StrategyOutcome(
            output={"extraction": CLAIM.handle().to_value()},
            resources=(
                (StrategyResourceBinding(kind=self._kind, identifier=digest),)
                if self._record
                else ()
            ),
        )


class RecordingModel:
    """A language model that records the prompts it is sent."""

    def __init__(
        self,
    ) -> None:
        self.prompts: list[Prompt] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt and answer."""

        self.prompts.append(prompt)

        return ModelResponse(
            text="December 14.",
            provider="test",
            model="recording",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )


def run_segment_then_prompt(
    *,
    record: bool,
    database: Path | None = None,
    kind: str = EXTRACTION_RESOURCE_KIND,
) -> tuple[WorkflowStepStatus, RecordingModel, str]:
    """Run a workflow that keeps an extraction, then prompts with it, journaling as it goes.

    Over a database, the journal, the store and the content access are its
    repositories', as every command's are.
    """

    model = RecordingModel()
    store: ContentStore

    if database is None:
        journal: RunJournalRepository = InMemoryRunJournalRepository()
        store = InMemoryContentStore()
        content = ToolContentAccess(
            store=store,
            initial_context=lambda run_id: journaled_initial_context(journal, run_id),
            kept_extractions=lambda run_id: journaled_extractions(journal, run_id),
        )
    else:
        repositories = open_repositories(database)
        journal = repositories.run_journal
        store = repositories.content
        content = repositories.tool_content

    workflow = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Read a claim",
            description="Keep an extraction of a claim, then ask about it.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=SEGMENT_STEP,
                strategy=KeepingStrategy(store, record=record, kind=kind),
                outputs=(WorkflowValueBinding(name="extraction", path=("extraction",)),),
            ),
            WorkflowCandidateStep(
                id=PROMPT_STEP,
                strategy=ContextPromptStrategy(
                    metadata=StrategyMetadata(
                        id=PROMPT_STEP,
                        name="ask",
                        description="Ask when the claim was received.",
                        version="1.0.0",
                    ),
                    template=PromptTemplate(
                        text="{claim}\n\nWhen was it received?",
                        bindings=(PromptInputBinding(variable_name="claim", input_name="claim"),),
                    ),
                    language_model=model,
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
            ),
        ),
    )
    runner = WorkflowRunner(journal=journal, content=content)
    result = asyncio.run(runner.run_recording_failures(workflow, Context()))

    return result.steps[1].status, model, json.dumps(result.model_dump(mode="json"))


def test_a_later_step_renders_an_extraction_an_earlier_step_kept() -> None:
    status, model, _ = run_segment_then_prompt(record=True)

    assert status is WorkflowStepStatus.EXECUTED
    assert model.prompts == [Prompt(text=f"{RENDERED_CLAIM}\n\nWhen was it received?")]


def test_a_handle_no_step_recorded_keeping_is_refused() -> None:
    status, model, recorded = run_segment_then_prompt(record=False)

    assert status is WorkflowStepStatus.FAILED
    assert model.prompts == []
    assert (
        f"Prompt strategy 'ask' shows extraction {CLAIM.digest()}, which no step of this run kept."
    ) in recorded


def test_a_commands_repositories_give_prompts_the_extractions_their_runs_kept(
    tmp_path: Path,
) -> None:
    status, model, _ = run_segment_then_prompt(record=True, database=tmp_path / "azathoth.db")

    assert status is WorkflowStepStatus.EXECUTED
    assert model.prompts == [Prompt(text=f"{RENDERED_CLAIM}\n\nWhen was it received?")]


def test_only_an_extraction_resource_records_keeping_an_extraction() -> None:
    status, model, _ = run_segment_then_prompt(record=True, kind="content")

    assert status is WorkflowStepStatus.FAILED
    assert model.prompts == []


def test_a_run_the_journal_does_not_know_kept_nothing() -> None:
    assert journaled_extractions(InMemoryRunJournalRepository(), ROOT_RUN) == frozenset()
