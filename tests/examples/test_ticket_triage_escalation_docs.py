"""Tests that the step confidence docs match the code and the example (ADR 0098)."""

import json
import re
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.workflows import (
    WorkflowCondition,
    WorkflowStepConfidenceError,
    decode_workflow_document,
    step_confidence,
)

PROJECT_ROOT = Path(__file__).parents[2]

TRIAGE_EXAMPLES = PROJECT_ROOT / "examples" / "ticket-triage"

TRIAGE_README = TRIAGE_EXAMPLES / "README.md"

ESCALATING_WORKFLOW_DOCUMENT = TRIAGE_EXAMPLES / "workflows" / "classify-ticket-escalating.json"

WORKFLOWS_README = PROJECT_ROOT / "src" / "azathoth" / "workflows" / "README.md"

CLI_README = PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md"

EXAMPLES_GUIDE = PROJECT_ROOT / "docs" / "examples.md"

ESCALATING_WORKFLOW_ID = "f1000000-0000-4000-8000-000000000070"

PLAIN_WORKFLOW_ID = "f1000000-0000-4000-8000-000000000010"

CLASSIFY_BENCHMARK_ID = "f1000000-0000-4000-8000-000000000050"


def section(
    path: Path,
    heading: str,
) -> str:
    """Return the text under one heading, up to the next heading of its level."""

    marker = heading.split(" ", 1)[0]
    text = path.read_text(encoding="utf-8").split(f"{heading}\n", 1)[1]
    following = re.search(rf"^{re.escape(marker)} ", text, re.MULTILINE)

    return text if following is None else text[: following.start()]


def code_blocks(
    text: str,
    language: str,
) -> tuple[str, ...]:
    """Return the bodies of one language's fenced blocks."""

    return tuple(re.findall(rf"```{language}\n(.*?)\n```", text, re.DOTALL))


def test_the_triage_readme_lists_the_escalating_classifier() -> None:
    assert (
        f"| `workflows/classify-ticket-escalating.json` | `{ESCALATING_WORKFLOW_ID}` |"
        in TRIAGE_README.read_text(encoding="utf-8")
    )


def test_the_documented_condition_is_the_workflows_condition() -> None:
    blocks = code_blocks(section(TRIAGE_README, "## Escalating When Unsure"), "json")

    (documented,) = (block for block in blocks if block.startswith('"conditions"'))

    conditions = json.loads("{" + documented + "}")["conditions"]

    escalate = decode_workflow_document(
        ESCALATING_WORKFLOW_DOCUMENT.read_text(encoding="utf-8")
    ).steps[0]

    assert tuple(WorkflowCondition.model_validate(item) for item in conditions) == (
        escalate.conditions
    )


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        (TRIAGE_README, "## Escalating When Unsure"),
        (EXAMPLES_GUIDE, "## 5. Ticket Triage: Routing"),
    ],
)
def test_the_documented_comparison_names_both_classifiers_and_the_benchmark(
    path: Path,
    heading: str,
) -> None:
    commands = " ".join(
        block.replace("\\\n", " ")
        for language in ("bash", "powershell")
        for block in code_blocks(section(path, heading), language)
    )

    (compare,) = set(
        re.findall(r"azathoth benchmark compare [^\n]*?--target-cost 0\.001", commands)
    )

    assert CLASSIFY_BENCHMARK_ID in compare
    assert f"--workflow {PLAIN_WORKFLOW_ID}" in compare
    assert f"--workflow {ESCALATING_WORKFLOW_ID}" in compare


def test_the_documented_confidence_error_is_the_one_raised() -> None:
    (documented,) = code_blocks(section(WORKFLOWS_README, "## Step Confidence"), "text")

    step_id = UUID(int=1)

    with pytest.raises(WorkflowStepConfidenceError) as raised:
        step_confidence(step_id, "confidence", 1.5)

    assert str(raised.value) == documented.replace("<STEP_ID>", str(step_id))


def test_the_documented_output_record_carries_a_confidence() -> None:
    (line,) = (
        line
        for line in CLI_README.read_text(encoding="utf-8").splitlines()
        if line.startswith('{"type": "output"') and "confidence" in line
    )

    record = json.loads(line)

    assert record["confidence"] == record["values"]["confidence"] == 0.62
