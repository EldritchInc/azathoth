"""Tests that the guide to reading documents shows what Azathoth really does (ADR 0112-0117).

The model-backed sections run against a scripted model that replies as the
guide shows a model replying; every other value they show is Azathoth's
own, from a real run of the example workflows on the example PDF.
"""

import json
import re
import shlex
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.citations import SegmentedText
from azathoth.cli import build_parser, main
from azathoth.inputs import file_uri
from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import (
    CitationPolicy,
    ContextPromptStrategySpec,
    PortfolioModelSelection,
    extraction_source,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.workflows import ToolStepSpecification, decode_workflow_document

PROJECT_ROOT = Path(__file__).parents[2]

GUIDE = PROJECT_ROOT / "docs" / "documents.md"

EXAMPLES = PROJECT_ROOT / "examples" / "documents"

CLAIM_PDF = EXAMPLES / "claim.pdf"

ANSWER_WORKFLOW = EXAMPLES / "answer-from-claim.json"

ANSWER_WORKFLOW_ID = "a1000000-0000-4000-8000-0000000000c2"

MODEL = ModelMetadata(
    provider="scripted",
    model="reader",
    display_name="Scripted Reader",
    context_window_tokens=32_768,
)

REPLY = {
    "received": {
        "answer": "December 14",
        "citation": {"source": "claim", "segment": "p1.s3", "quote": "received on December 14"},
    },
    "approved": {
        "answer": "$1,200",
        "citation": {"source": "claim", "segment": "p2.s2", "quote": "approved up to $1,200"},
    },
}
"""The reply the guide shows a model giving: each answer, and the citation behind it."""


def blocks(
    language: str,
) -> list[str]:
    """Return the guide's fenced blocks in one language."""

    return re.findall(rf"```{language}\n(.*?)```", GUIDE.read_text(encoding="utf-8"), re.DOTALL)


def filled(
    shown: str,
    *,
    extraction_digest: str,
) -> str:
    """Return a block the guide shows, its placeholders filled as this run fills them."""

    return (
        shown.replace("file:///<CHECKOUT>/examples/documents/claim.pdf", file_uri(CLAIM_PDF))
        .replace("<PDFMINER_VERSION>", version("pdfminer.six"))
        .replace("<EXTRACTION_DIGEST>", extraction_digest)
    )


def run(
    *arguments: str,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Run one CLI command, requiring success; return its output."""

    status = main(arguments)
    captured = capsys.readouterr()

    assert status == 0, captured.err

    return captured.out


@pytest.fixture
def walked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    """Walk the guide's sections 2 to 4 against a scripted model; return what each printed."""

    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(PROJECT_ROOT)
    monkeypatch.setattr(
        cli_bootstrap, "_load_current_models", lambda _configuration: ModelCatalog(models=(MODEL,))
    )
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(
            {
                MODEL.identifier: DeterministicLanguageModel(
                    provider=MODEL.provider, model=MODEL.model, response_text=json.dumps(REPLY)
                )
            }
        ),
    )

    run("init", capsys=capsys)
    run("model", "authorize", MODEL.identifier, capsys=capsys)

    for line in (*blocks("bash")[1].splitlines(), *blocks("bash")[2].splitlines()):
        if " workflow import " in f" {line} ":
            run(*shlex.split(line)[1:], capsys=capsys)

    segmented = json.loads(run(*shlex.split(blocks("bash")[1].splitlines()[1])[1:], capsys=capsys))
    answered = json.loads(run(*shlex.split(blocks("bash")[2].splitlines()[1])[1:], capsys=capsys))
    (listed,) = run(*shlex.split(blocks("bash")[3].splitlines()[0])[1:], capsys=capsys).splitlines()
    run_id = listed.split()[0]
    annotations = json.loads(run("run", "annotations", run_id, capsys=capsys))

    return {
        "segmented": segmented,
        "answered": answered,
        "annotations": annotations,
        "database": tmp_path / "azathoth.db",
    }


def test_the_guide_is_one_of_the_user_guides() -> None:
    documents = (PROJECT_ROOT / "tests" / "test_docs.py").read_text(encoding="utf-8")

    assert '"docs/documents.md",' in documents


def test_the_answering_workflow_cites_from_the_segmenting_step_and_names_no_model() -> None:
    workflow = decode_workflow_document(ANSWER_WORKFLOW.read_text(encoding="utf-8"))
    (segment, answer) = workflow.steps

    assert str(workflow.metadata.id) == ANSWER_WORKFLOW_ID
    assert isinstance(segment.specification, ToolStepSpecification)
    assert segment.specification.requirement.name == "segment_pdf"
    assert isinstance(answer.specification, ContextPromptStrategySpec)
    assert answer.specification.citations == CitationPolicy(on_unverified="fail")
    assert isinstance(answer.specification.model_selection, PortfolioModelSelection)
    assert answer.retry_policy.max_attempts == 2
    assert answer.specification.output_format.value == "json"

    (shown,) = (json.loads(block) for block in blocks("json")[:1])

    assert shown == {
        "output_format": "json",
        "citations": answer.specification.citations.model_dump(mode="json"),
    }


def test_the_segmenting_run_prints_the_line_the_guide_shows(
    walked: dict[str, Any],
) -> None:
    extraction = walked["segmented"]["extraction"]
    shown = blocks("text")[0].strip()

    assert json.dumps(walked["segmented"]) == filled(shown, extraction_digest=extraction["digest"])


def test_the_segments_are_shown_as_the_prompt_shows_them(
    walked: dict[str, Any],
) -> None:
    digest = walked["segmented"]["extraction"]["digest"]
    kept = open_repositories(walked["database"]).content.get(digest)

    assert kept is not None
    assert blocks("text")[1] == (
        extraction_source("claim", SegmentedText.model_validate_json(kept)) + "\n"
    )


def test_the_answer_shown_is_the_runs_first_answer_with_its_check(
    walked: dict[str, Any],
) -> None:
    received = walked["answered"]["received"]
    digest = received["citation"]["anchor"]["extraction"]["digest"]
    shown = json.loads(filled(blocks("json")[1], extraction_digest=digest))

    assert shown == {"received": received}
    assert walked["answered"]["approved"]["citation"]["status"] == "verified"


def test_the_annotation_target_shown_is_the_second_citations(
    walked: dict[str, Any],
) -> None:
    collection = walked["annotations"]
    (_, second) = collection["first"]["items"]
    shown = json.loads(filled(blocks("json")[2], extraction_digest=""))

    assert collection["total"] == 2
    assert collection["label"].endswith(": 2 verified.")
    assert second["target"] == shown


def test_the_refusals_quoted_are_the_ones_the_engine_gives() -> None:
    adr = (PROJECT_ROOT / "docs" / "adrs" / "0116-cited-prompt-steps.md").read_text(
        encoding="utf-8"
    )

    for line in blocks("text")[2].splitlines():
        assert line in adr


@pytest.mark.parametrize("language", ["bash", "powershell"])
def test_every_azathoth_command_shown_parses(
    language: str,
) -> None:
    commands = [
        line
        for block in blocks(language)
        for line in block.splitlines()
        if line.startswith("azathoth ")
    ]

    assert len(commands) == 6

    for command in commands:
        filled_in = command.replace("<RUN_ID>", "00000000-0000-4000-8000-000000000001")
        build_parser().parse_args(shlex.split(filled_in)[1:])


def test_both_platforms_run_the_same_commands() -> None:
    assert [block for block in blocks("bash")] == [block for block in blocks("powershell")]
