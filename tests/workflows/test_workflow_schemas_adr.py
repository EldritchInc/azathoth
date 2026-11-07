"""Tests that ADR 0118 quotes the real refusals and the real shape of declared schemas."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from azathoth.workflows import WorkflowSpecification, decode_workflow_document
from tests.workflows.test_promotion import WORKFLOW_ID, create_workflow

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0118-workflow-input-and-output-schemas.md"


def refusal(
    **fields: Any,
) -> str:
    """Return the message the promotion workflow with some fields is refused with."""

    with pytest.raises(ValidationError) as raised:
        WorkflowSpecification.model_validate(
            {**create_workflow().model_dump(mode="json"), **fields}
        )

    return (
        str(raised.value.errors()[0]["msg"])
        .removeprefix("Value error, ")
        .replace("A JSON Schema must be an object or a boolean.", "<REASON>")
        .replace(str(WORKFLOW_ID), "<WORKFLOW_ID>")
    )


DOCUMENTED: list[tuple[str, Callable[[], str]]] = [
    (
        "The workflow's input schema is not usable: <REASON>",
        lambda: refusal(input_schema=3),
    ),
    (
        "The workflow's output schema is not usable: <REASON>",
        lambda: refusal(output_schema=3),
    ),
    (
        "Workflow <WORKFLOW_ID> has an output schema, which describes its result, but "
        "declares no result.",
        lambda: refusal(result=None, output_schema=True),
    ),
]
"""Each refusal ADR 0118 quotes, and what produces it."""


def decision_blocks(
    language: str,
) -> list[str]:
    """Return the ADR's Decision blocks in one language."""

    text = ADR.read_text(encoding="utf-8")
    decision = text[text.index("## Decision") : text.index("## Consequences")]

    return [block.split("```", 1)[0] for block in decision.split(f"```{language}\n")[1:]]


@pytest.mark.parametrize(
    ("documented", "produce"),
    [pytest.param(*row, id=row[0][:48]) for row in DOCUMENTED],
)
def test_the_adr_quotes_the_real_refusal(
    documented: str,
    produce: Callable[[], str],
) -> None:
    assert f"\n{documented}\n" in ADR.read_text(encoding="utf-8")
    assert produce() == documented


def test_the_adr_quotes_no_text_the_tests_do_not_check() -> None:
    quoted = {line for block in decision_blocks("text") for line in block.splitlines()}

    assert quoted == {documented for documented, _ in DOCUMENTED}


def test_the_adr_shows_schemas_a_workflow_accepts() -> None:
    (shown,) = decision_blocks("json")
    schemas = {
        key: value
        for key, value in json.loads(shown).items()
        if key in ("input_schema", "output_schema")
    }
    workflow = create_workflow().model_dump(mode="json")

    assert set(schemas) == {"input_schema", "output_schema"}
    assert (
        decode_workflow_document(json.dumps({**workflow, **schemas})).input_schema
        == (schemas["input_schema"])
    )


def test_the_adr_is_listed_in_the_index() -> None:
    index = (ROOT / "docs" / "adrs" / "README.md").read_text(encoding="utf-8")

    assert (
        "- [ADR 0118: Workflow Input and Output Schemas]"
        "(0118-workflow-input-and-output-schemas.md)\n" in index
    )
