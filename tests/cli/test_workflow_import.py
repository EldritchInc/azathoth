"""Tests for importing workflow JSON documents through the CLI."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    import_workflow,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    encode_workflow_document,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_workflow() -> WorkflowSpecification:
    """Create one workflow for import tests."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="imported workflow",
            description=("Exercise CLI workflow document import."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="import prompt",
                        description="Exercise workflow import.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def configure_database(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure one test database for CLI import."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def write_workflow_document(
    path: Path,
) -> None:
    """Write one valid workflow document."""

    path.write_text(
        encode_workflow_document(create_workflow()),
        encoding="utf-8",
    )


def test_workflow_import_persists_valid_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "workflow.json"

    write_workflow_document(document)

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = import_workflow(document)

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (f"Imported workflow {WORKFLOW_ID}.\n")

    assert captured.err == ""

    restored = SQLiteWorkflowRepository(database).get(WORKFLOW_ID)

    assert restored == create_workflow()


def test_workflow_import_reports_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "missing.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = import_workflow(document)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert f"Unable to read workflow document {document}:" in captured.err

    assert not database.exists()


def test_workflow_import_rejects_malformed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "workflow.json"

    document.write_text(
        "{definitely not json",
        encoding="utf-8",
    )

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = import_workflow(document)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == ("Workflow document is not a valid WorkflowSpecification.\n")

    assert not database.exists()


def test_workflow_import_rejects_invalid_workflow_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "workflow.json"

    document.write_text(
        """
{
  "metadata": {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "",
    "description": "Invalid workflow.",
    "version": "1.0.0"
  },
  "steps": []
}
""".strip(),
        encoding="utf-8",
    )

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = import_workflow(document)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == ("Workflow document is not a valid WorkflowSpecification.\n")

    assert not database.exists()


def test_workflow_import_rejects_duplicate_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "workflow.json"

    write_workflow_document(document)

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    assert import_workflow(document) == 0

    capsys.readouterr()

    result = import_workflow(document)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Workflow specification {WORKFLOW_ID} already exists.\n")

    assert SQLiteWorkflowRepository(database).specifications() == (create_workflow(),)


def test_workflow_import_does_not_require_provider_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "workflow.json"

    write_workflow_document(document)

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    monkeypatch.delenv(
        "OPENROUTER_API_KEY",
        raising=False,
    )

    result = import_workflow(document)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
