"""Promote and invoke every self-contained model-backed example through the CLI.

Each example is driven through the commands an operator runs: import its
tools and workflow, authorize its model, promote it, and invoke it. Each
example's own scripted model stands in for the provider, so the invocation
result is the one the example's tests already expect.

Workflows that loop over child workflows (write-chapter, edit-queue and
write-novel) are not covered here. Their children are separate artifacts,
promoted and invoked on their own, and run as separate processes that a
scripted model cannot reach.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    main,
)
from azathoth.providers import (
    LanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.tools import encode_tool_document
from azathoth.workflows import decode_workflow_document
from tests.examples.test_classify_sentiment_examples import (
    WORKFLOW_DOCUMENT as SENTIMENT_WORKFLOW_DOCUMENT,
)
from tests.examples.test_classify_sentiment_examples import (
    KeywordSentimentModel,
)
from tests.examples.test_code_review_examples import (
    CHANGE,
    REVIEW_WORKFLOW_DOCUMENT,
    review_model,
)
from tests.examples.test_code_review_examples import (
    FINALIZE_TOOL_DOCUMENT as REVIEW_FINALIZE_TOOL_DOCUMENT,
)
from tests.examples.test_code_review_examples import (
    MERGE_TOOL_DOCUMENT as REVIEW_MERGE_TOOL_DOCUMENT,
)
from tests.examples.test_novel_revision_examples import (
    APPLY_MARKER,
    CHAPTER,
    CONTEXT,
    ECHO_TOOL_DOCUMENT,
    PACK_TOOL_DOCUMENT,
    REQUESTS,
    REVISE_WORKFLOW_DOCUMENT,
    REVISED,
    VERIFY_MARKER,
    RoutingLanguageModel,
)
from tests.examples.test_ticket_triage_examples import (
    CLASSIFY_WORKFLOW_DOCUMENT,
    TRIAGE_WORKFLOW_DOCUMENT,
    TriageModel,
    scripted_catalog,
)
from tests.examples.test_ticket_triage_examples import (
    FINALIZE_TOOL_DOCUMENT as TRIAGE_FINALIZE_TOOL_DOCUMENT,
)
from tests.examples.test_workflow_writer_examples import (
    FINALIZE_TOOL_DOCUMENT as WRITER_FINALIZE_TOOL_DOCUMENT,
)
from tests.examples.test_workflow_writer_examples import (
    REQUEST,
    WRITE_WORKFLOW_DOCUMENT,
    reference_workflow,
    runnable_validator,
    writer_model,
)


@dataclass(frozen=True)
class ExampleCli:
    """Run CLI commands against an isolated database with scripted models."""

    tmp_path: Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]

    def configure(
        self,
        *,
        models: ModelCatalog,
        registry: LanguageModelRegistry,
    ) -> None:
        """Give the real CLI runtime the example's scripted models."""

        self.monkeypatch.setenv(
            DATABASE_ENVIRONMENT_VARIABLE,
            str(self.tmp_path / "azathoth.db"),
        )

        self.monkeypatch.setattr(
            cli_bootstrap,
            "_load_current_models",
            lambda _configuration: models,
        )

        self.monkeypatch.setattr(
            cli_bootstrap,
            "_load_language_models",
            lambda *, configuration, models: registry,
        )

    def run(
        self,
        *arguments: str,
    ) -> str:
        """Run one CLI command, require success, and return its standard output."""

        status = main(arguments)
        captured = self.capsys.readouterr()

        assert status == 0, captured.err

        return captured.out


@pytest.fixture
def cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> ExampleCli:
    """Return a CLI runner against an isolated database."""

    return ExampleCli(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )


def workflow_id(
    path: Path,
) -> UUID:
    """Return the ID of one checked-in workflow."""

    return decode_workflow_document(path.read_text(encoding="utf-8")).metadata.id


def promote_and_invoke(
    cli: ExampleCli,
    *,
    workflow: Path,
    tools: tuple[Path, ...],
    models: ModelCatalog,
    language_model: LanguageModel,
    payloads: tuple[JsonValue, ...],
) -> list[JsonValue]:
    """Import, authorize, promote and invoke one example; return each invocation's output."""

    (model,) = models.models

    cli.configure(
        models=models,
        registry=LanguageModelRegistry(models={model.identifier: language_model}),
    )

    for tool in tools:
        cli.run("tool", "import", str(tool))

    cli.run("workflow", "import", str(workflow))
    cli.run("model", "authorize", model.identifier)

    identifier = str(workflow_id(workflow))

    cli.run("workflow", "promote", identifier)

    return [
        json.loads(
            cli.run(
                "workflow",
                "invoke",
                identifier,
                "--input",
                json.dumps(payload),
                "--output",
                "result",
            )
        )
        for payload in payloads
    ]


def novelist_catalog() -> ModelCatalog:
    """Return the one scripted long-context model the routing examples use."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="scripted",
                model="novelist",
                display_name="Scripted Novelist",
                context_window_tokens=1_000_000,
            ),
        ),
    )


def test_classify_sentiment_promotes_and_invokes(
    cli: ExampleCli,
) -> None:
    results = promote_and_invoke(
        cli,
        workflow=SENTIMENT_WORKFLOW_DOCUMENT,
        tools=(),
        models=ModelCatalog(
            models=(
                ModelMetadata(
                    provider="deterministic",
                    model="sentiment",
                    display_name="Deterministic Sentiment",
                    context_window_tokens=8_192,
                ),
            ),
        ),
        language_model=KeywordSentimentModel(),
        payloads=(
            "The checkout flow was painless.",
            "The staff was rude and the food was cold.",
        ),
    )

    assert results == [
        {"result": "positive"},
        {"result": "negative"},
    ]


def test_classify_ticket_promotes_and_invokes(
    cli: ExampleCli,
) -> None:
    results = promote_and_invoke(
        cli,
        workflow=CLASSIFY_WORKFLOW_DOCUMENT,
        tools=(),
        models=scripted_catalog(("triage", 1.0)),
        language_model=TriageModel(),
        payloads=(
            {
                "subject": "Charged twice",
                "body": "My card was charged twice for the March invoice.",
                "customer_tier": "standard",
            },
        ),
    )

    assert results == [{"result": "billing"}]


def test_triage_ticket_promotes_and_invokes(
    cli: ExampleCli,
) -> None:
    results = promote_and_invoke(
        cli,
        workflow=TRIAGE_WORKFLOW_DOCUMENT,
        tools=(TRIAGE_FINALIZE_TOOL_DOCUMENT,),
        models=scripted_catalog(("triage", 1.0)),
        language_model=TriageModel(),
        payloads=(
            {
                "subject": "Locked out",
                "body": "Details.",
                "customer_tier": "standard",
            },
        ),
    )

    assert results == [
        {
            "result": {
                "category": "account",
                "urgency": "normal",
                "summary": "A account issue.",
                "reply": "Reply from the account specialist.",
                "approved": True,
                "problems": [],
                "needs_human": False,
            }
        }
    ]


def test_write_workflow_promotes_and_invokes(
    cli: ExampleCli,
) -> None:
    validator = cli.tmp_path / "validate-workflow.json"
    validator.write_text(encode_tool_document(runnable_validator()), encoding="utf-8")

    results = promote_and_invoke(
        cli,
        workflow=WRITE_WORKFLOW_DOCUMENT,
        tools=(validator, WRITER_FINALIZE_TOOL_DOCUMENT),
        models=novelist_catalog(),
        language_model=writer_model(reference_workflow()),
        payloads=(REQUEST,),
    )

    assert results == [
        {
            "result": {
                "valid": True,
                "errors": "",
                "workflow": reference_workflow(),
            }
        }
    ]


def test_review_change_promotes_and_invokes(
    cli: ExampleCli,
) -> None:
    results = promote_and_invoke(
        cli,
        workflow=REVIEW_WORKFLOW_DOCUMENT,
        tools=(REVIEW_MERGE_TOOL_DOCUMENT, REVIEW_FINALIZE_TOOL_DOCUMENT),
        models=novelist_catalog(),
        language_model=review_model(),
        payloads=(CHANGE,),
    )

    assert results == [
        {
            "result": {
                "verdict": "approve",
                "findings": [],
                "counts": {"high": 0, "medium": 0, "low": 0},
                "summary": "No issues found.",
            }
        }
    ]


def test_revise_chapter_promotes_and_invokes(
    cli: ExampleCli,
) -> None:
    results = promote_and_invoke(
        cli,
        workflow=REVISE_WORKFLOW_DOCUMENT,
        tools=(ECHO_TOOL_DOCUMENT, PACK_TOOL_DOCUMENT),
        models=novelist_catalog(),
        language_model=RoutingLanguageModel(
            (
                (APPLY_MARKER, REVISED),
                (VERIFY_MARKER, '{"unmet": []}'),
            )
        ),
        payloads=(
            {
                "state": {"chapter": CHAPTER, "requests": list(REQUESTS), "context": CONTEXT},
                "iteration": 1,
            },
        ),
    )

    assert results == [
        {
            "result": {
                "state": {"chapter": REVISED, "requests": [], "context": CONTEXT},
                "done": True,
                "item": 0,
            }
        }
    ]
