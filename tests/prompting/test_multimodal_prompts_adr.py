"""Tests that ADR 0115 quotes the real refusals of prompts that show content."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import (
    Context,
    ContextEvent,
    LineageRun,
    LineageStep,
    StepLineage,
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
    WORKFLOW_INPUT_BOUND_EVENT_TYPE,
    ContextPromptStrategy,
    ModelBinding,
    PromptInputBinding,
    PromptStrategySpec,
    PromptTemplate,
    read_prompt_content,
)
from azathoth.providers import (
    BedrockLanguageModel,
    ContentPart,
    DeterministicLanguageModel,
    ModelExecutionError,
    ModelModality,
    Prompt,
    TextPart,
    giving_prompt_content,
    prompt_content_bytes,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolContentAccess, providing_tool_content
from azathoth.workflows import create_workflow_input_events
from tests.providers.fake_bedrock import FakeBedrockClient

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0115-multimodal-prompts.md"

RUN = UUID("c1510000-0000-4000-8000-000000000010")

PDF = b"%PDF-1.7\n%%EOF\n"

DOCUMENT = ContentRef(
    digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    size_bytes=len(PDF),
)

SHOWING = Prompt(parts=(ContentPart(content=DOCUMENT),))


def received(
    media_type: str = "application/pdf",
) -> Context:
    """Return an initial context that received the PDF under one media type."""

    return Context(
        events=tuple(
            create_workflow_input_events(
                ResolvedInput(
                    value=DOCUMENT.to_value(),
                    media_type=media_type,
                    provenance=InputProvenance(
                        uri="file:///claims/claim-0412.pdf",
                        media_type=media_type,
                        size_bytes=len(PDF),
                        digest=DOCUMENT.digest,
                    ),
                ),
                producer="azathoth.cli",
            )
        )
    )


def refusal(
    prompt: Prompt = SHOWING,
    *,
    context: Context | None = None,
    stored: bytes | None = PDF,
    give_access: bool = True,
    in_step: bool = True,
) -> str:
    """Return the message read_prompt_content refuses a prompt with."""

    store = InMemoryContentStore()

    if stored is not None:
        store.put(stored)

    initial = context if context is not None else received()
    access = ToolContentAccess(store=store, initial_context={RUN: initial}.get)
    step = StepLineage(
        step=LineageStep(workflow_id=RUN, run_id=RUN, step_id=RUN, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=RUN, run_id=RUN),
    )

    async def go() -> None:
        await read_prompt_content(prompt, strategy_name="<NAME>")

    def call() -> None:
        if in_step:
            with running_step(step):
                asyncio.run(go())
        else:
            asyncio.run(go())

    with pytest.raises(ModelExecutionError) as raised:
        if give_access:
            with providing_tool_content(access):
                call()
        else:
            call()

    return str(raised.value)


def tampered_refusal() -> str:
    """Return the message content changed under its digest is refused with."""

    class Tampered(InMemoryContentStore):
        """A store whose content was changed under its digest."""

        def get(self, digest: str) -> bytes | None:
            return b"%PDF-1.7 tampered"

    access = ToolContentAccess(store=Tampered(), initial_context={RUN: received()}.get)
    step = StepLineage(
        step=LineageStep(workflow_id=RUN, run_id=RUN, step_id=RUN, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=RUN, run_id=RUN),
    )

    async def go() -> None:
        await read_prompt_content(SHOWING, strategy_name="<NAME>")

    with (
        providing_tool_content(access),
        running_step(step),
        pytest.raises(ModelExecutionError) as raised,
    ):
        asyncio.run(go())

    return str(raised.value)


def fixed_prompt_refusal() -> str:
    """Return the message a fixed prompt that shows content is refused with."""

    with pytest.raises(ValidationError) as raised:
        PromptStrategySpec.model_validate(
            {
                "metadata": {
                    "id": str(RUN),
                    "name": "<NAME>",
                    "description": "Show a document.",
                    "version": "1.0.0",
                },
                "prompt": SHOWING.model_dump(mode="json"),
                "model_selection": {"provider": "deterministic", "model": "deterministic"},
            }
        )

    return raised.value.errors()[0]["msg"].removeprefix("Value error, ")


def prompt_refusal(
    value: dict[str, object],
) -> str:
    """Return the message a prompt of one shape is refused with."""

    with pytest.raises(ValidationError) as raised:
        Prompt.model_validate(value)

    return raised.value.errors()[0]["msg"].removeprefix("Value error, ")


def bedrock_refusal(
    prompt: Prompt,
    given: dict[str, bytes],
) -> str:
    """Return the message a Bedrock model refuses a prompt of parts with."""

    with giving_prompt_content(given), pytest.raises(ModelExecutionError) as raised:
        asyncio.run(BedrockLanguageModel(FakeBedrockClient(), "<MODEL>").complete(prompt))

    return str(raised.value)


def many(
    count: int,
    content: bytes,
    media_type: str,
) -> tuple[Prompt, dict[str, bytes]]:
    """Return a prompt of text and some distinct pieces of one kind of content."""

    pieces = [content + bytes([index]) for index in range(count)]
    handles = [
        ContentRef(digest=content_bytes_digest(piece), media_type=media_type, size_bytes=len(piece))
        for piece in pieces
    ]

    return (
        Prompt(parts=(TextPart(text="Look:"), *(ContentPart(content=shown) for shown in handles))),
        {shown.digest: piece for shown, piece in zip(handles, pieces, strict=True)},
    )


def oversized(
    content: bytes,
    media_type: str,
    limit: int,
) -> tuple[Prompt, dict[str, bytes], str]:
    """Return a prompt of text and one piece of content a byte over a limit, and its digest."""

    piece = content + b"\x00" * (limit - len(content) + 1)
    shown = ContentRef(
        digest=content_bytes_digest(piece),
        media_type=media_type,
        size_bytes=len(piece),
    )

    return (
        Prompt(parts=(TextPart(text="Look:"), ContentPart(content=shown))),
        {shown.digest: piece},
        shown.digest,
    )


PNG = b"\x89PNG\r\n\x1a\n"

BIG_IMAGE = oversized(PNG, "image/png", 3_750_000)

BIG_DOCUMENT = oversized(PDF, "application/pdf", 4_500_000)


def unreadable_refusal() -> str:
    """Return the message a model that does not read PDFs is refused one with."""

    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(
            id=RUN,
            name="<NAME>",
            description="Show a document.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text="Read {document}",
            bindings=(PromptInputBinding(variable_name="document", input_name="document"),),
        ),
        language_model=DeterministicLanguageModel(),
        model_binding=ModelBinding(identifier="<MODEL>"),
        model_input_modalities=frozenset({ModelModality.TEXT}),
    )
    context = Context(
        events=(
            ContextEvent(
                event_type=WORKFLOW_INPUT_BOUND_EVENT_TYPE,
                payload={"name": "document", "value": DOCUMENT.to_value()},
                producer="workflow-runner",
            ),
        )
    )

    with pytest.raises(ModelExecutionError) as raised:
        asyncio.run(strategy.run(context))

    return str(raised.value)


def missing_bytes() -> str:
    """Return the message a provider gives for bytes it was not given."""

    with pytest.raises(ModelExecutionError) as raised:
        prompt_content_bytes(DOCUMENT, model="<PROVIDER>/<MODEL>")

    return str(raised.value)


DIGEST = DOCUMENT.digest

DOCUMENTED: list[tuple[str, Callable[[], str], dict[str, str]]] = [
    (
        "A prompt holds its text, or parts that show content.",
        lambda: prompt_refusal({}),
        {},
    ),
    (
        "A prompt holds its text or its parts, not both.",
        lambda: prompt_refusal({"text": "x", **SHOWING.model_dump(mode="json")}),
        {},
    ),
    (
        "A prompt's parts show content; a prompt of text alone holds it as its text.",
        lambda: prompt_refusal({"parts": [{"text": "x"}]}),
        {},
    ),
    (
        "Prompt strategy '<NAME>' shows content in a fixed prompt; content reaches a prompt "
        "only through a template variable bound to a content handle.",
        fixed_prompt_refusal,
        {},
    ),
    (
        "Prompt strategy '<NAME>' shows content, which this run cannot give: "
        "it has no content store.",
        lambda: refusal(give_access=False),
        {},
    ),
    (
        "Prompt strategy '<NAME>' shows content, which only a workflow step can give.",
        lambda: refusal(in_step=False),
        {},
    ),
    (
        "Prompt strategy '<NAME>' shows content <DIGEST>, which this run never received.",
        lambda: refusal(context=Context()),
        {"<DIGEST>": DIGEST},
    ),
    (
        "Prompt strategy '<NAME>' shows content <DIGEST> as <MEDIA_TYPE>, but this run "
        "received it as <MEDIA_TYPES>.",
        lambda: refusal(context=received("image/png")),
        {"<DIGEST>": DIGEST, "<MEDIA_TYPE>": "application/pdf", "<MEDIA_TYPES>": "image/png"},
    ),
    (
        "Content <DIGEST> is not in the content store.",
        lambda: refusal(stored=None),
        {"<DIGEST>": DIGEST},
    ),
    (
        "Content <DIGEST> in the content store does not match its digest.",
        tampered_refusal,
        {"<DIGEST>": DIGEST},
    ),
    (
        "Prompt strategy '<NAME>' shows content <DIGEST> as <SIZE> bytes, but it holds <ACTUAL>.",
        lambda: refusal(
            Prompt(parts=(ContentPart(content=DOCUMENT.model_copy(update={"size_bytes": 1})),))
        ),
        {"<DIGEST>": DIGEST, "<SIZE>": "1", "<ACTUAL>": str(len(PDF))},
    ),
    (
        "Prompt strategy '<NAME>' shows content <DIGEST> as <MEDIA_TYPE>, but model <MODEL> "
        "does not take <MODALITY> input.",
        unreadable_refusal,
        {"<DIGEST>": DIGEST, "<MEDIA_TYPE>": "application/pdf", "<MODALITY>": "file"},
    ),
    (
        "Model <PROVIDER>/<MODEL> was not given the bytes of content <DIGEST>.",
        missing_bytes,
        {"<DIGEST>": DIGEST},
    ),
    (
        "Bedrock model '<MODEL>' is shown at most 20 images in one prompt; this one shows <COUNT>.",
        lambda: bedrock_refusal(*many(21, PNG, "image/png")),
        {"<COUNT>": "21"},
    ),
    (
        "Bedrock model '<MODEL>' is shown at most 5 documents in one prompt; this one shows "
        "<COUNT>.",
        lambda: bedrock_refusal(*many(6, PDF, "application/pdf")),
        {"<COUNT>": "6"},
    ),
    (
        "Bedrock model '<MODEL>' is shown images of at most 3750000 bytes; content <DIGEST> "
        "is <SIZE>.",
        lambda: bedrock_refusal(BIG_IMAGE[0], BIG_IMAGE[1]),
        {"<DIGEST>": BIG_IMAGE[2], "<SIZE>": "3750001"},
    ),
    (
        "Bedrock model '<MODEL>' is shown documents of at most 4500000 bytes; content "
        "<DIGEST> is <SIZE>.",
        lambda: bedrock_refusal(BIG_DOCUMENT[0], BIG_DOCUMENT[1]),
        {"<DIGEST>": BIG_DOCUMENT[2], "<SIZE>": "4500001"},
    ),
    (
        "Bedrock model '<MODEL>' is shown a document only beside text; this prompt has none.",
        lambda: bedrock_refusal(SHOWING, {DOCUMENT.digest: PDF}),
        {},
    ),
]
"""Each message ADR 0115 quotes, what produces it, and its placeholders' values."""


@pytest.mark.parametrize(
    ("documented", "produce", "values"),
    [pytest.param(*row, id=row[0][:48]) for row in DOCUMENTED],
)
def test_the_adr_quotes_the_real_message(
    documented: str,
    produce: Callable[[], str],
    values: dict[str, str],
) -> None:
    expected = documented

    for placeholder, value in values.items():
        expected = expected.replace(placeholder, value)

    assert f"\n{documented}\n" in ADR.read_text(encoding="utf-8")
    assert produce() == expected


def test_the_adr_quotes_no_message_the_tests_do_not_check() -> None:
    text = ADR.read_text(encoding="utf-8")
    decision = text[text.index("## Decision") : text.index("## Consequences")]
    quoted = {
        line
        for block in decision.split("```text\n")[1:]
        for line in block.split("```", 1)[0].splitlines()
    }

    assert quoted == {documented for documented, _, _ in DOCUMENTED}


def test_the_adr_is_listed_in_the_index() -> None:
    index = (ROOT / "docs" / "adrs" / "README.md").read_text(encoding="utf-8")

    assert "- [ADR 0115: Multimodal Prompts](0115-multimodal-prompts.md)\n" in index
