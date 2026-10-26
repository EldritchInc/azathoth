"""Tests proving the word-count benchmark example and its add-case walkthrough."""

from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    main,
)
from azathoth.evaluation import (
    BenchmarkDataset,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.workflows import (
    SOURCE_FEEDBACK_METADATA_KEY,
    SOURCE_RUN_METADATA_KEY,
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    WorkflowRun,
)
from tests.examples.test_redundant_word_count_examples import (
    PROCESS_TOOL_DOCUMENT,
    PYTHON_TOOL_DOCUMENT,
)
from tests.examples.test_word_count_messages_examples import (
    WORKFLOW_DOCUMENT,
    WORKFLOW_ID,
)

PROJECT_ROOT = Path(__file__).parents[2]

BENCHMARK_DOCUMENT = PROJECT_ROOT / "examples" / "benchmarks" / "word-count.json"

BENCHMARK_ID = UUID("b1000000-0000-4000-8000-000000000001")

CASE_ID = UUID("b1000000-0000-4000-8000-000000000011")

DASHED_TEXT = "the old ones wait — and dream"


def read_benchmark() -> BenchmarkDataset:
    """Decode the checked-in word-count benchmark."""

    return decode_benchmark_document(
        BENCHMARK_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )


def configure_walkthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at an isolated database with no provider models."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(),
    )

    return database


def run_cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> str:
    """Run one CLI command that must succeed, returning its standard output."""

    status = main(arguments)

    captured = capsys.readouterr()

    assert status == 0, captured.err

    output: str = captured.out

    return output


def import_examples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Import both word-count tools, the step-messages workflow, and the benchmark."""

    run_cli(capsys, "tool", "import", str(PYTHON_TOOL_DOCUMENT))
    run_cli(capsys, "tool", "import", str(PROCESS_TOOL_DOCUMENT))
    run_cli(capsys, "workflow", "import", str(WORKFLOW_DOCUMENT))
    run_cli(capsys, "benchmark", "import", str(BENCHMARK_DOCUMENT))


def only_run(
    database: Path,
) -> WorkflowRun:
    """Return the single configured run of the example workflow."""

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID)

    assert len(runs) == 1

    return runs[0]


def test_word_count_benchmark_example_is_canonical() -> None:
    document = BENCHMARK_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert document.rstrip("\n") == encode_benchmark_document(read_benchmark())


def test_word_count_benchmark_example_declares_one_exact_case() -> None:
    dataset = read_benchmark()

    assert dataset.id == BENCHMARK_ID
    assert tuple(case.id for case in dataset.cases) == (CASE_ID,)

    (case,) = dataset.cases

    assert case.input == "that is not dead which can eternal lie"
    assert case.expected.value == 8
    assert case.expected.comparison is OutcomeComparison.EXACT


def test_word_count_benchmark_example_passes_against_the_example_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_walkthrough(
        monkeypatch,
        tmp_path,
    )

    import_examples(capsys)

    rendered = run_cli(
        capsys,
        "benchmark",
        "run",
        str(BENCHMARK_ID),
        "--workflow",
        str(WORKFLOW_ID),
    )

    assert "Cases Run: 1\n" in rendered
    assert "Cases Passed: 1\n" in rendered


def test_add_case_walkthrough_captures_a_corrected_run_as_a_benchmark_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_walkthrough(
        monkeypatch,
        tmp_path,
    )

    import_examples(capsys)

    assert (
        run_cli(
            capsys,
            "workflow",
            "run",
            str(WORKFLOW_ID),
            "--input",
            f'"{DASHED_TEXT}"',
            "--output",
            "result",
        )
        == "7\n"
    )

    run = only_run(database)

    run_cli(
        capsys,
        "run",
        "feedback",
        str(run.id),
        "--bad",
        "--reason",
        "A dash is not a word.",
        "--corrected-output",
        "6",
    )

    (feedback,) = SQLiteWorkflowRunFeedbackRepository(database).feedback_for_run(run.id)

    added = run_cli(
        capsys,
        "benchmark",
        "add-case",
        str(BENCHMARK_ID),
        "--from-run",
        str(run.id),
        "--comparison",
        "exact",
        "--description",
        "Dashes are not words.",
    )

    dataset = SQLiteBenchmarkRepository(database).get(BENCHMARK_ID)

    assert dataset is not None
    assert tuple(case.id for case in dataset.cases)[0] == CASE_ID
    assert len(dataset.cases) == 2

    case = dataset.cases[-1]

    assert added == (
        f"Added benchmark case {case.id} to benchmark dataset {BENCHMARK_ID} revision 2.\n"
    )

    assert case.input == DASHED_TEXT
    assert case.expected.value == 6
    assert case.expected.comparison is OutcomeComparison.EXACT
    assert case.expected.description == "Dashes are not words."
    assert case.metadata == {
        SOURCE_RUN_METADATA_KEY: str(run.id),
        SOURCE_FEEDBACK_METADATA_KEY: str(feedback.id),
    }

    history = run_cli(
        capsys,
        "benchmark",
        "history",
        str(BENCHMARK_ID),
    ).splitlines()

    assert len(history) == 2
    assert history[0].startswith("2  ")
    assert "  2 cases  word count" in history[0]
    assert history[1].startswith("1  ")
    assert "  1 cases  word count" in history[1]

    rendered = run_cli(
        capsys,
        "benchmark",
        "run",
        str(BENCHMARK_ID),
        "--workflow",
        str(WORKFLOW_ID),
    )

    assert "Cases Run: 2\n" in rendered
    assert "Cases Passed: 1\n" in rendered
