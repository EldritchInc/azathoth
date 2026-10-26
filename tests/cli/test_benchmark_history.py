"""Tests for inspecting and exporting imported benchmark revisions."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    build_parser,
    export_benchmark,
    import_benchmark,
    list_benchmark_history,
    show_benchmark,
)
from azathoth.cli.dispatching import dispatch_benchmark_command
from azathoth.evaluation import (
    BenchmarkDatasetRevision,
    SQLiteBenchmarkRepository,
    encode_benchmark_document,
)
from tests.cli.test_benchmark_import import (
    BENCHMARK_ID,
    configure_database,
    create_dataset,
)
from tests.evaluation.test_benchmark_revision_repository import (
    create_changed_dataset,
    create_legacy_database,
)

UNKNOWN_BENCHMARK_ID = UUID("99999999-9999-4999-8999-999999999999")


def save_history(
    database: Path,
) -> tuple[BenchmarkDatasetRevision, ...]:
    """Import the benchmark, change it, then revert the change."""

    repository = SQLiteBenchmarkRepository(database)

    return (
        repository.save(create_dataset()),
        repository.save(create_changed_dataset()),
        repository.save(create_dataset()),
    )


def history_line(
    revision: BenchmarkDatasetRevision,
    *,
    note: str = "",
) -> str:
    """Return the expected history line of one revision."""

    imported = revision.imported_at.isoformat() if revision.imported_at else "unknown"

    dataset = revision.dataset

    return (
        f"{revision.number}  {imported}  {revision.content_digest[:12]}  "
        f"{dataset.version}  {len(dataset.cases)} cases  {dataset.name}{note}"
    )


def unused(
    *_arguments: object,
    **_keywords: object,
) -> int:
    """Fail when an unrelated benchmark handler is dispatched."""

    raise AssertionError("unrelated benchmark handler should not be dispatched")


def dispatch(
    arguments: Namespace,
    *,
    export_benchmark: Callable[..., int] = unused,
    list_benchmark_history: Callable[..., int] = unused,
    show_benchmark: Callable[..., int] = unused,
) -> int | None:
    """Dispatch one benchmark command with only the revision handlers live."""

    return dispatch_benchmark_command(
        arguments,
        add_benchmark_case=unused,
        compare_benchmarks=unused,
        export_benchmark=export_benchmark,
        import_benchmark=unused,
        list_benchmark_cases=unused,
        list_benchmark_executions=unused,
        list_benchmark_history=list_benchmark_history,
        list_benchmarks=unused,
        run_benchmark=unused,
        show_benchmark=show_benchmark,
        show_benchmark_case=unused,
        show_benchmark_execution=unused,
    )


def test_history_parser_records_benchmark_and_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "history",
            str(BENCHMARK_ID),
            "--limit",
            "2",
        )
    )

    assert arguments.benchmark_action == "history"
    assert arguments.benchmark_id == BENCHMARK_ID
    assert arguments.benchmark_history_limit == 2


def test_show_and_export_parsers_record_a_revision() -> None:
    for action in ("show", "export"):
        arguments = build_parser().parse_args(
            (
                "benchmark",
                action,
                str(BENCHMARK_ID),
                "--revision",
                "2",
            )
        )

        assert arguments.benchmark_action == action
        assert arguments.benchmark_revision == 2


def test_show_parser_defaults_to_the_latest_revision() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "show",
            str(BENCHMARK_ID),
        )
    )

    assert arguments.benchmark_revision is None


def test_revision_dispatch_passes_revisions_and_limits() -> None:
    calls: list[tuple[str, UUID, int | None]] = []

    def recorder(
        name: str,
        keyword: str,
    ) -> Callable[..., int]:
        def handler(
            benchmark_id: UUID,
            **keywords: int | None,
        ) -> int:
            calls.append((name, benchmark_id, keywords[keyword]))

            return 0

        return handler

    dispatch(
        Namespace(
            benchmark_action="show",
            benchmark_id=BENCHMARK_ID,
            benchmark_revision=2,
        ),
        show_benchmark=recorder("show", "revision"),
    )

    dispatch(
        Namespace(
            benchmark_action="export",
            benchmark_id=BENCHMARK_ID,
            benchmark_revision=None,
        ),
        export_benchmark=recorder("export", "revision"),
    )

    dispatch(
        Namespace(
            benchmark_action="history",
            benchmark_id=BENCHMARK_ID,
            benchmark_history_limit=4,
        ),
        list_benchmark_history=recorder("history", "limit"),
    )

    assert calls == [
        ("show", BENCHMARK_ID, 2),
        ("export", BENCHMARK_ID, None),
        ("history", BENCHMARK_ID, 4),
    ]


def test_history_lists_revisions_newest_first_and_names_reverts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    first, changed, reverted = save_history(database)

    status = list_benchmark_history(BENCHMARK_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""
    assert captured.out.splitlines() == [
        history_line(reverted, note="  identical to revision 1"),
        history_line(changed),
        history_line(first),
    ]


def test_history_applies_the_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    assert list_benchmark_history(BENCHMARK_ID, limit=1) == 0
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_history_shows_unknown_import_time_for_migrated_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    create_legacy_database(
        database,
        create_dataset(),
    )

    assert list_benchmark_history(BENCHMARK_ID) == 0
    assert capsys.readouterr().out.startswith("1  unknown  ")


def test_history_rejects_an_unknown_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(
        database=tmp_path / "azathoth.db",
        monkeypatch=monkeypatch,
    )

    assert list_benchmark_history(UNKNOWN_BENCHMARK_ID) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Benchmark dataset {UNKNOWN_BENCHMARK_ID} is not configured.\n"


def test_show_names_the_revision_shown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    _first, changed, reverted = save_history(database)

    assert show_benchmark(BENCHMARK_ID) == 0

    latest_output = capsys.readouterr().out

    assert latest_output.startswith(
        f"ID: {BENCHMARK_ID}\n"
        "Revision: 3 of 3\n"
        f"Imported: {reverted.imported_at.isoformat() if reverted.imported_at else ''}\n"
        f"Content Digest: {reverted.content_digest}\n"
    )
    assert "Cases: 1\n" in latest_output

    assert show_benchmark(BENCHMARK_ID, revision=2) == 0

    earlier_output = capsys.readouterr().out

    assert "Revision: 2 of 3\n" in earlier_output
    assert f"Content Digest: {changed.content_digest}\n" in earlier_output
    assert "Cases: 0\n" in earlier_output


def test_show_rejects_an_unknown_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    assert show_benchmark(BENCHMARK_ID, revision=4) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Benchmark dataset {BENCHMARK_ID} has no revision 4.\n"


def test_export_prints_the_latest_or_a_chosen_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    assert export_benchmark(BENCHMARK_ID) == 0
    assert capsys.readouterr().out == encode_benchmark_document(create_dataset()) + "\n"

    assert export_benchmark(BENCHMARK_ID, revision=2) == 0
    assert capsys.readouterr().out == encode_benchmark_document(create_changed_dataset()) + "\n"


def test_exported_revisions_reimport_as_identical_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    export_benchmark(BENCHMARK_ID, revision=2)

    document = tmp_path / "revision-2.json"

    document.write_text(
        capsys.readouterr().out,
        encoding="utf-8",
    )

    assert import_benchmark(document) == 0
    assert capsys.readouterr().out == (
        f"Imported benchmark dataset {BENCHMARK_ID} revision 4 (identical to revision 2).\n"
    )
    assert SQLiteBenchmarkRepository(database).get(BENCHMARK_ID) == create_changed_dataset()


def test_export_rejects_unknown_benchmarks_and_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    assert export_benchmark(UNKNOWN_BENCHMARK_ID) == 1
    assert capsys.readouterr().err == (
        f"Benchmark dataset {UNKNOWN_BENCHMARK_ID} is not configured.\n"
    )

    assert export_benchmark(BENCHMARK_ID, revision=9) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Benchmark dataset {BENCHMARK_ID} has no revision 9.\n"
