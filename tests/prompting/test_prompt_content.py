"""Tests for prompts that show a model content its run received (ADR 0115)."""

import asyncio
import json
from collections.abc import Callable
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

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
from azathoth.inputs import (
    ContentRef,
    InMemoryContentStore,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.prompting import (
    ContextPromptStrategy,
    PromptBinding,
    PromptInputBinding,
    PromptStrategySpec,
    PromptTemplate,
    read_prompt_content,
)
from azathoth.prompting.execution import execute_prompt
from azathoth.providers import (
    ContentPart,
    ModelResponse,
    Prompt,
    PromptContentError,
    TextPart,
    prompt_content_bytes,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolContentAccess, providing_tool_content
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepStatus,
    create_workflow_input_events,
)

WORKFLOW_ID = UUID("c1500000-0000-4000-8000-000000000001")

STEP_ID = UUID("c1500000-0000-4000-8000-000000000002")

STRATEGY_ID = UUID("c1500000-0000-4000-8000-000000000003")

ROOT_RUN = UUID("c1500000-0000-4000-8000-000000000010")

CHILD_RUN = UUID("c1500000-0000-4000-8000-000000000011")

BOUND_EVENT_TYPE = "workflow.input.bound"
"""The event a workflow step binds each input with."""

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

DOCUMENT = ContentRef(
    digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    size_bytes=len(PDF),
)

PHOTO = ContentRef(
    digest=content_bytes_digest(PNG),
    media_type="image/png",
    size_bytes=len(PNG),
)


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


def template(
    text: str,
    *names: str,
) -> PromptTemplate:
    """Return a template binding each name to the step input of that name."""

    return PromptTemplate(
        text=text,
        bindings=tuple(PromptInputBinding(variable_name=name, input_name=name) for name in names),
    )


def resolved_context(
    *contents: tuple[bytes, str],
    lineage_parent: UUID | None = None,
) -> Context:
    """Return a run's initial context, as an entry point records a reference to each content."""

    events: list[ContextEvent] = []

    for content, media_type in contents:
        digest = content_bytes_digest(content)
        events.extend(
            create_workflow_input_events(
                ResolvedInput(
                    value={
                        "content": {
                            "digest": digest,
                            "media_type": media_type,
                            "size_bytes": len(content),
                        }
                    },
                    media_type=media_type,
                    provenance=InputProvenance(
                        uri="file:///claims/claim-0412",
                        media_type=media_type,
                        size_bytes=len(content),
                        digest=digest,
                    ),
                ),
                producer="azathoth.cli",
            )
        )

    if lineage_parent is not None:
        events.append(
            create_lineage_event(
                WorkflowLineage(
                    depth=1,
                    parent=LineageStep(
                        workflow_id=WORKFLOW_ID,
                        run_id=lineage_parent,
                        step_id=STEP_ID,
                        attempt=1,
                    ),
                    root=LineageRun(workflow_id=WORKFLOW_ID, run_id=ROOT_RUN),
                )
            )
        )

    return Context(events=tuple(events))


def access(
    runs: dict[UUID, Context] | None = None,
    *,
    content: tuple[bytes, ...] = (PDF, PNG),
) -> ToolContentAccess:
    """Return content access over a store holding some content."""

    store = InMemoryContentStore()

    for item in content:
        store.put(item)

    known = (
        runs
        if runs is not None
        else {ROOT_RUN: resolved_context((PDF, "application/pdf"), (PNG, "image/png"))}
    )

    return ToolContentAccess(store=store, initial_context=known.get)


def any_run(
    initial: Context,
) -> ToolContentAccess:
    """Return content access that knows every run, whatever its ID, by one initial context."""

    return ToolContentAccess(
        store=access().store,
        initial_context=lambda run_id: initial,
    )


def step(
    run_id: UUID = ROOT_RUN,
) -> StepLineage:
    """Return the lineage of a step of one run."""

    return StepLineage(
        step=LineageStep(workflow_id=WORKFLOW_ID, run_id=run_id, step_id=STEP_ID, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=WORKFLOW_ID, run_id=ROOT_RUN),
    )


def read(
    prompt: Prompt,
    *,
    content: ToolContentAccess | None = None,
    run_id: UUID | None = ROOT_RUN,
    strategy_name: str | None = "describe_claim",
) -> dict[str, bytes]:
    """Read a prompt's content as a running step of one run would."""

    async def go() -> dict[str, bytes]:
        return await read_prompt_content(prompt, strategy_name=strategy_name)

    def in_step() -> dict[str, bytes]:
        if run_id is None:
            return asyncio.run(go())

        with running_step(step(run_id)):
            return asyncio.run(go())

    if content is None:
        return in_step()

    with providing_tool_content(content):
        return in_step()


def showing(
    *contents: ContentRef,
) -> Prompt:
    """Return a prompt that shows each content after a line of text."""

    return Prompt(
        parts=tuple(
            part
            for content in contents
            for part in (TextPart(text="Look:\n"), ContentPart(content=content))
        )
    )


def test_a_template_that_binds_no_content_renders_text_as_it_always_did() -> None:
    prompt = template("Classify {ticket}.", "ticket").render(bound(ticket="My printer is on fire"))

    assert prompt == Prompt(text="Classify My printer is on fire.")
    assert prompt.model_dump(mode="json") == {"text": "Classify My printer is on fire."}


def test_a_variable_bound_to_content_shows_it_where_the_variable_stands() -> None:
    prompt = template(
        "Here is the claim form:\n{form}\nand the photo:\n{photo}\nDo they match?",
        "form",
        "photo",
    ).render(bound(form=DOCUMENT.to_value(), photo=PHOTO.to_value()))

    assert prompt == Prompt(
        parts=(
            TextPart(text="Here is the claim form:\n"),
            ContentPart(content=DOCUMENT),
            TextPart(text="\nand the photo:\n"),
            ContentPart(content=PHOTO),
            TextPart(text="\nDo they match?"),
        )
    )


def test_content_at_either_end_leaves_no_empty_text() -> None:
    prompt = template("{photo}{form}", "photo", "form").render(
        bound(photo=PHOTO.to_value(), form=DOCUMENT.to_value())
    )

    assert prompt.parts == (ContentPart(content=PHOTO), ContentPart(content=DOCUMENT))


def test_a_variable_used_twice_shows_its_content_twice() -> None:
    prompt = template("{photo} and again {photo}", "photo").render(bound(photo=PHOTO.to_value()))

    assert prompt.parts == (
        ContentPart(content=PHOTO),
        TextPart(text=" and again "),
        ContentPart(content=PHOTO),
    )


def test_text_and_content_variables_mix() -> None:
    prompt = template("Ticket {ticket}: {photo}", "ticket", "photo").render(
        bound(ticket={"id": 412}, photo=PHOTO.to_value())
    )

    assert prompt.parts == (TextPart(text='Ticket {"id":412}: '), ContentPart(content=PHOTO))


def test_an_event_field_bound_to_content_shows_it() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="workflow.input.received",
                payload={"input": DOCUMENT.to_value()},
                producer="azathoth.cli",
            ),
        )
    )
    prompt = PromptTemplate(
        text="Read {document}",
        bindings=(
            PromptBinding(
                variable_name="document",
                event_type="workflow.input.received",
                field_name="input",
            ),
        ),
    ).render(context)

    assert prompt.parts == (TextPart(text="Read "), ContentPart(content=DOCUMENT))


def test_a_template_that_never_places_its_content_variable_renders_text() -> None:
    prompt = template("No pictures today.", "photo").render(bound(photo=PHOTO.to_value()))

    assert prompt == Prompt(text="No pictures today.")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param([PHOTO.to_value()], id="list-of-handles"),
        pytest.param({"photo": PHOTO.to_value()}, id="handle-inside-an-object"),
        pytest.param({**PHOTO.to_value(), "note": "x"}, id="handle-with-more-keys"),
        pytest.param(
            {"content": {"digest": "0" * 64, "media_type": "text/plain", "size_bytes": 1}},
            id="not-a-binary-handle",
        ),
    ],
)
def test_only_a_value_that_is_exactly_one_handle_is_content(
    value: JsonValue,
) -> None:
    prompt = template("See {photo}", "photo").render(bound(photo=value))

    assert prompt == Prompt(
        text="See " + json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )


def test_text_a_value_carries_cannot_stand_for_content() -> None:
    forged = "\x00" + "0" * 32 + ":0\x00"
    prompt = template("{photo} {note}", "photo", "note").render(
        bound(photo=PHOTO.to_value(), note=forged)
    )

    assert prompt.parts == (ContentPart(content=PHOTO), TextPart(text=" " + forged))


def test_each_rendering_draws_its_own_markers() -> None:
    text = template("{note}", "note")
    first = text.render(bound(note="\x00plain\x00"))

    assert first == Prompt(text="\x00plain\x00")


def test_a_fixed_prompt_cannot_show_content() -> None:
    with pytest.raises(ValidationError) as raised:
        PromptStrategySpec.model_validate(
            {
                "metadata": {
                    "id": str(STRATEGY_ID),
                    "name": "describe_claim",
                    "description": "Describe a claim.",
                    "version": "1.0.0",
                },
                "prompt": showing(DOCUMENT).model_dump(mode="json"),
                "model_selection": {"provider": "deterministic", "model": "deterministic"},
            }
        )

    assert (
        "Prompt strategy 'describe_claim' shows content in a fixed prompt; content reaches "
        "a prompt only through a template variable bound to a content handle."
    ) in str(raised.value)


def test_a_fixed_prompt_of_text_is_unchanged() -> None:
    specification = PromptStrategySpec.model_validate(
        {
            "metadata": {
                "id": str(STRATEGY_ID),
                "name": "describe_claim",
                "description": "Describe a claim.",
                "version": "1.0.0",
            },
            "prompt": {"text": "Describe a claim."},
            "model_selection": {"provider": "deterministic", "model": "deterministic"},
        }
    )

    assert specification.model_dump(mode="json")["prompt"] == {"text": "Describe a claim."}


def test_a_prompt_of_text_reads_nothing_and_needs_no_access() -> None:
    assert read(Prompt(text="Hello."), content=None, run_id=None) == {}


def test_content_a_run_received_is_read_once_by_digest() -> None:
    prompt = Prompt(
        parts=(
            ContentPart(content=DOCUMENT),
            ContentPart(content=PHOTO),
            ContentPart(content=DOCUMENT),
        )
    )

    assert read(prompt, content=access()) == {DOCUMENT.digest: PDF, PHOTO.digest: PNG}


def test_a_child_reads_content_its_parent_received() -> None:
    runs = {
        ROOT_RUN: resolved_context((PDF, "application/pdf")),
        CHILD_RUN: resolved_context(lineage_parent=ROOT_RUN),
    }

    assert read(showing(DOCUMENT), content=access(runs), run_id=CHILD_RUN) == {DOCUMENT.digest: PDF}


ShownError = Callable[[], dict[str, bytes]]


@pytest.mark.parametrize(
    ("attempt", "message"),
    [
        pytest.param(
            lambda: read(showing(DOCUMENT), content=None),
            "Prompt strategy 'describe_claim' shows content, which this run cannot give: "
            "it has no content store.",
            id="no-access",
        ),
        pytest.param(
            lambda: read(showing(DOCUMENT), content=access(), run_id=None),
            "Prompt strategy 'describe_claim' shows content, which only a workflow step can give.",
            id="no-step",
        ),
        pytest.param(
            lambda: read(showing(DOCUMENT), content=None, strategy_name=None),
            "A prompt shows content, which this run cannot give: it has no content store.",
            id="no-strategy-name",
        ),
        pytest.param(
            lambda: read(
                showing(DOCUMENT),
                content=access({ROOT_RUN: resolved_context((PNG, "image/png"))}),
            ),
            f"Prompt strategy 'describe_claim' shows content {DOCUMENT.digest}, "
            "which this run never received.",
            id="never-received",
        ),
        pytest.param(
            lambda: read(
                showing(DOCUMENT),
                content=access({CHILD_RUN: resolved_context((PDF, "application/pdf"))}),
            ),
            f"Prompt strategy 'describe_claim' shows content {DOCUMENT.digest}, "
            "which this run never received.",
            id="another-run-received-it",
        ),
        pytest.param(
            lambda: read(
                showing(DOCUMENT.model_copy(update={"media_type": "image/png"})),
                content=access(),
            ),
            f"Prompt strategy 'describe_claim' shows content {DOCUMENT.digest} as image/png, "
            "but this run received it as application/pdf.",
            id="other-media-type",
        ),
        pytest.param(
            lambda: read(showing(DOCUMENT), content=access(content=(PNG,))),
            f"Content {DOCUMENT.digest} is not in the content store.",
            id="not-in-store",
        ),
        pytest.param(
            lambda: read(
                showing(DOCUMENT.model_copy(update={"size_bytes": 3})),
                content=access(),
            ),
            f"Prompt strategy 'describe_claim' shows content {DOCUMENT.digest} as 3 bytes, "
            f"but it holds {len(PDF)}.",
            id="other-size",
        ),
    ],
)
def test_content_a_prompt_cannot_show_is_refused(
    attempt: ShownError,
    message: str,
) -> None:
    with pytest.raises(PromptContentError) as raised:
        attempt()

    assert str(raised.value) == message


def test_content_that_does_not_match_its_digest_is_refused() -> None:
    class Tampered(InMemoryContentStore):
        """A store whose content was changed under its digest."""

        def get(self, digest: str) -> bytes | None:
            return b"%PDF-1.7 tampered"

    tampered = ToolContentAccess(
        store=Tampered(),
        initial_context={ROOT_RUN: resolved_context((PDF, "application/pdf"))}.get,
    )

    with pytest.raises(PromptContentError) as raised:
        read(showing(DOCUMENT), content=tampered)

    assert str(raised.value) == (
        f"Content {DOCUMENT.digest} in the content store does not match its digest."
    )


def test_a_second_showing_is_checked_against_its_own_size() -> None:
    prompt = Prompt(
        parts=(
            ContentPart(content=DOCUMENT),
            ContentPart(content=DOCUMENT.model_copy(update={"size_bytes": 1})),
        )
    )

    with pytest.raises(PromptContentError) as raised:
        read(prompt, content=access())

    assert str(raised.value) == (
        f"Prompt strategy 'describe_claim' shows content {DOCUMENT.digest} as 1 bytes, "
        f"but it holds {len(PDF)}."
    )


class SeeingModel:
    """A language model that records what it is shown and the bytes it can read."""

    def __init__(
        self,
    ) -> None:
        self.prompts: list[Prompt] = []
        self.seen: list[dict[str, bytes]] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt and the bytes of each content it shows."""

        self.prompts.append(prompt)
        self.seen.append(
            {
                content.digest: prompt_content_bytes(content, model="test/seeing")
                for content in prompt.contents()
            }
        )

        return ModelResponse(
            text="It matches.",
            provider="test",
            model="seeing",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )


def test_the_model_reads_the_bytes_only_while_it_is_called() -> None:
    model = SeeingModel()

    async def go() -> None:
        await execute_prompt(prompt=showing(PHOTO), language_model=model, model_binding=None)

    with providing_tool_content(access()), running_step(step()):
        asyncio.run(go())

    assert model.seen == [{PHOTO.digest: PNG}]

    with pytest.raises(PromptContentError):
        prompt_content_bytes(PHOTO, model="test/seeing")


def test_a_prompt_that_cannot_show_its_content_never_calls_the_model() -> None:
    model = SeeingModel()

    async def go() -> None:
        await execute_prompt(
            prompt=showing(DOCUMENT),
            language_model=model,
            model_binding=None,
            strategy_name="describe_claim",
        )

    runs = {ROOT_RUN: resolved_context((PNG, "image/png"))}

    with (
        providing_tool_content(access(runs)),
        running_step(step()),
        pytest.raises(PromptContentError),
    ):
        asyncio.run(go())

    assert model.prompts == []


def describing(
    model: SeeingModel,
) -> WorkflowCandidate:
    """Return a workflow of one prompt step that shows the model the workflow's input."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Describe a claim",
            description="Show a model the workflow's document.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=ContextPromptStrategy(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="describe_claim",
                        description="Describe the claim the workflow was given.",
                        version="1.0.0",
                    ),
                    template=PromptTemplate(
                        text="Describe this claim:\n{document}",
                        bindings=(
                            PromptBinding(
                                variable_name="document",
                                event_type="workflow.input.received",
                                field_name="input",
                            ),
                        ),
                    ),
                    language_model=model,
                ),
            ),
        ),
    )


def test_a_runner_given_content_access_shows_its_prompt_steps_the_content() -> None:
    initial = resolved_context((PDF, "application/pdf"))
    model = SeeingModel()

    run = asyncio.run(
        WorkflowRunner(content=any_run(initial)).run(
            workflow=describing(model),
            context=initial,
        )
    )

    assert run.steps[0].status is WorkflowStepStatus.EXECUTED
    assert model.prompts == [
        Prompt(parts=(TextPart(text="Describe this claim:\n"), ContentPart(content=DOCUMENT)))
    ]
    assert model.seen == [{DOCUMENT.digest: PDF}]


def test_a_runner_without_content_access_fails_a_prompt_step_that_shows_content() -> None:
    model = SeeingModel()
    run = asyncio.run(
        WorkflowRunner().run_recording_failures(
            describing(model),
            resolved_context((PDF, "application/pdf")),
        )
    )

    assert run.steps[0].status is WorkflowStepStatus.FAILED
    assert "shows content, which this run cannot give: it has no content store" in json.dumps(
        run.model_dump(mode="json")
    )
    assert model.prompts == []


def test_a_recorded_run_names_the_content_and_never_holds_its_bytes() -> None:
    initial = resolved_context((PDF, "application/pdf"))
    run = asyncio.run(
        WorkflowRunner(content=any_run(initial)).run(
            workflow=describing(SeeingModel()),
            context=initial,
        )
    )
    recorded = run.model_dump_json()

    assert "%PDF-1.7" not in recorded
    assert "JVBERi0xLjcK" not in recorded


def test_content_shown_more_than_once_is_read_from_the_store_once() -> None:
    class Counting(InMemoryContentStore):
        """A store that counts the reads of each digest."""

        def __init__(self) -> None:
            super().__init__()
            self.reads: list[str] = []

        def get(self, digest: str) -> bytes | None:
            self.reads.append(digest)
            return super().get(digest)

    store = Counting()
    store.put(PDF)
    store.put(PNG)
    counting = ToolContentAccess(
        store=store,
        initial_context={
            ROOT_RUN: resolved_context((PDF, "application/pdf"), (PNG, "image/png"))
        }.get,
    )
    prompt = Prompt(
        parts=(
            ContentPart(content=DOCUMENT),
            ContentPart(content=PHOTO),
            ContentPart(content=DOCUMENT),
            ContentPart(content=PHOTO),
        )
    )

    read(prompt, content=counting)

    assert store.reads == [DOCUMENT.digest, PHOTO.digest]
