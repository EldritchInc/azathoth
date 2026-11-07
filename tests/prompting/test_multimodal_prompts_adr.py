"""Tests that ADR 0115 quotes the real refusals of prompts that show content."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context, LineageRun, LineageStep, StepLineage, running_step
from azathoth.inputs import (
    ContentRef,
    InMemoryContentStore,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.prompting import PromptStrategySpec, read_prompt_content
from azathoth.providers import (
    BedrockLanguageModel,
    ContentPart,
    ModelExecutionError,
    Prompt,
    prompt_content_bytes,
)
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


def bedrock_refusal() -> str:
    """Return the message Bedrock refuses a prompt of parts with."""

    with pytest.raises(ModelExecutionError) as raised:
        asyncio.run(BedrockLanguageModel(FakeBedrockClient(), "<MODEL>").complete(SHOWING))

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
        "Model <PROVIDER>/<MODEL> was not given the bytes of content <DIGEST>.",
        missing_bytes,
        {"<DIGEST>": DIGEST},
    ),
    (
        "Bedrock model '<MODEL>' cannot be shown content by this release.",
        bedrock_refusal,
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
