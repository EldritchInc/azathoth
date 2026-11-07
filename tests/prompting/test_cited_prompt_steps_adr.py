"""Tests that ADR 0116 quotes the real rendering and refusals of extractions in prompts."""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.citations import ExtractionHandle, Segment, SegmentedText
from azathoth.context import Context, LineageRun, LineageStep, StepLineage, running_step
from azathoth.inputs import InMemoryContentStore, content_bytes_digest
from azathoth.prompting import render_extraction
from azathoth.providers import PromptContentError
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
