"""Tests for browsing saved benchmark executions through the CLI."""

from argparse import Namespace
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.benchmarks as benchmark_commands
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    build_parser,
    list_benchmark_executions,
    show_benchmark_execution,
)
from azathoth.cli.dispatching import dispatch_benchmark_command
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.workflows import (
    SQLiteWorkflowBenchmarkExecutionRepository,
    WorkflowBenchmarkExecutionRecord,
)
from tests.cli.test_benchmark_execution_rendering import (
    BENCHMARK_ID,
    EXACT_CASE_ID,
    RECORDED_AT,
    create_comparison,
    create_run,
)

OLDEST_EXECUTION_ID = UUID("0e0e0e0e-0000-4000-8000-000000000001")
MIDDLE_EXECUTION_ID = UUID("0e0e0e0e-0000-4000-8000-000000000002")
NEWEST_EXECUTION_ID = UUID("0e0e0e0e-0000-4000-8000-000000000003")

OTHER_BENCHMARK_ID = UUID("0b0b0b0b-0000-4000-8000-000000000001")

UNKNOWN_ID = UUID("99999999-9999-4999-8999-999999999999")


def configure_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at one isolated database and forbid runtime bootstrap."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    def fail_load_runtime(
        _configuration: object,
    ) -> object:
        raise AssertionError("browsing saved executions must not bootstrap the runtime")

    monkeypatch.setattr(
        benchmark_commands,
        "load_runtime",
        fail_load_runtime,
    )

    return database


def save_dataset(
    database: Path,
) -> None:
    """Persist the benchmark the saved executions ran."""

    SQLiteBenchmarkRepository(database).save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="saved-executions",
            description="Benchmark with saved executions.",
            cases=(
                BenchmarkCase(
                    id=EXACT_CASE_ID,
                    input="first",
                    expected=ExpectedOutcome(
                        description="The answer.",
                        value="positive",
                        comparison=OutcomeComparison.EXACT,
                    ),
                ),
            ),
        )
    )


def save_executions(
    database: Path,
) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
    """Save three executions of the benchmark and one of another.

    They are saved out of time order, so listings prove they sort by
    recorded time rather than by insertion.
    """

    middle = create_run().model_copy(
        update={
            "id": MIDDLE_EXECUTION_ID,
            "recorded_at": RECORDED_AT + timedelta(minutes=1),
        },
    )

    newest = create_comparison().model_copy(
        update={
            "id": NEWEST_EXECUTION_ID,
            "recorded_at": RECORDED_AT + timedelta(minutes=2),
        },
    )

    oldest = create_comparison().model_copy(
        update={
            "id": OLDEST_EXECUTION_ID,
        },
    )

    other = create_run().model_copy(
        update={
            "benchmark_id": OTHER_BENCHMARK_ID,
        },
    )

    repository = SQLiteWorkflowBenchmarkExecutionRepository(database)

    for execution in (
        middle,
        newest,
        other,
        oldest,
    ):
        repository.save(execution)

    return newest, middle, oldest


def listed_ids(
    output: str,
) -> list[str]:
    """Return the execution ID leading each listed line."""

    return [line.split()[0] for line in output.splitlines()]


def unused(
    *_arguments: object,
    **_keywords: object,
) -> int:
    """Fail when an unrelated benchmark handler is dispatched."""

    raise AssertionError("unrelated benchmark handler should not be dispatched")


def dispatch(
    arguments: Namespace,
    *,
    list_benchmark_executions: Callable[..., int] = unused,
    show_benchmark_execution: Callable[[UUID], int] = unused,
) -> int | None:
    """Dispatch one benchmark command with only the execution handlers live."""

    return dispatch_benchmark_command(
        arguments,
        compare_benchmarks=unused,
        export_benchmark=unused,
        import_benchmark=unused,
        list_benchmark_cases=unused,
        list_benchmark_executions=list_benchmark_executions,
        list_benchmark_history=unused,
        list_benchmarks=unused,
        run_benchmark=unused,
        show_benchmark=unused,
        show_benchmark_case=unused,
        show_benchmark_execution=show_benchmark_execution,
    )


def test_executions_parser_records_benchmark_without_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "executions",
            str(BENCHMARK_ID),
        )
    )

    assert arguments.benchmark_action == "executions"
    assert arguments.benchmark_id == BENCHMARK_ID
    assert arguments.benchmark_execution_limit is None


def test_executions_parser_records_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "executions",
            str(BENCHMARK_ID),
            "--limit",
            "2",
        )
    )

    assert arguments.benchmark_execution_limit == 2


def test_executions_parser_rejects_non_positive_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(
            (
                "benchmark",
                "executions",
                str(BENCHMARK_ID),
                "--limit",
                "0",
            )
        )

    assert raised.value.code == 2
    assert "Expected a positive integer, got '0'." in capsys.readouterr().err


def test_execution_show_parser_records_execution() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "execution-show",
            str(NEWEST_EXECUTION_ID),
        )
    )

    assert arguments.benchmark_action == "execution-show"
    assert arguments.benchmark_execution_id == NEWEST_EXECUTION_ID


def test_executions_dispatch_passes_benchmark_and_limit() -> None:
    calls: list[tuple[UUID, int | None]] = []

    def list_executions(
        benchmark_id: UUID,
        *,
        limit: int | None,
    ) -> int:
        calls.append((benchmark_id, limit))

        return 13

    result = dispatch(
        Namespace(
            benchmark_action="executions",
            benchmark_id=BENCHMARK_ID,
            benchmark_execution_limit=3,
        ),
        list_benchmark_executions=list_executions,
    )

    assert result == 13
    assert calls == [(BENCHMARK_ID, 3)]


def test_execution_show_dispatch_passes_execution() -> None:
    calls: list[UUID] = []

    def show_execution(
        execution_id: UUID,
    ) -> int:
        calls.append(execution_id)

        return 11

    result = dispatch(
        Namespace(
            benchmark_action="execution-show",
            benchmark_execution_id=NEWEST_EXECUTION_ID,
        ),
        show_benchmark_execution=show_execution,
    )

    assert result == 11
    assert calls == [NEWEST_EXECUTION_ID]


def test_list_benchmark_executions_lists_newest_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_dataset(database)
    save_executions(database)

    status = list_benchmark_executions(BENCHMARK_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""
    assert listed_ids(captured.out) == [
        str(NEWEST_EXECUTION_ID),
        str(MIDDLE_EXECUTION_ID),
        str(OLDEST_EXECUTION_ID),
    ]
    assert "  compare  2 candidates  2 cases  winner " in captured.out.splitlines()[0]
    assert "  run  1 candidate  2 cases  workflow " in captured.out.splitlines()[1]


def test_list_benchmark_executions_applies_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_dataset(database)
    save_executions(database)

    status = list_benchmark_executions(
        BENCHMARK_ID,
        limit=2,
    )

    assert status == 0
    assert listed_ids(capsys.readouterr().out) == [
        str(NEWEST_EXECUTION_ID),
        str(MIDDLE_EXECUTION_ID),
    ]


def test_list_benchmark_executions_keeps_executions_of_removed_benchmarks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_executions(database)

    status = list_benchmark_executions(BENCHMARK_ID)

    assert status == 0
    assert len(listed_ids(capsys.readouterr().out)) == 3


def test_list_benchmark_executions_of_unexecuted_benchmark_prints_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_dataset(database)

    status = list_benchmark_executions(BENCHMARK_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.out == ""
    assert captured.err == ""


def test_list_benchmark_executions_rejects_unknown_benchmark(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(
        monkeypatch,
        tmp_path,
    )

    status = list_benchmark_executions(UNKNOWN_ID)

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == f"Benchmark dataset {UNKNOWN_ID} is not configured.\n"


def test_show_benchmark_execution_renders_the_saved_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    newest, _middle, _oldest = save_executions(database)

    status = show_benchmark_execution(NEWEST_EXECUTION_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""
    assert captured.out.startswith(
        f"Execution ID: {NEWEST_EXECUTION_ID}\nRecorded: 2026-10-23T12:32:00+00:00\nKind: compare\n"
    )

    for candidate in newest.candidates:
        for case in candidate.cases:
            assert f"run {case.run_id}  evaluation {case.evaluation_id}" in captured.out


def test_show_benchmark_execution_rejects_unknown_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(
        monkeypatch,
        tmp_path,
    )

    status = show_benchmark_execution(UNKNOWN_ID)

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == f"Benchmark execution {UNKNOWN_ID} was not found.\n"
