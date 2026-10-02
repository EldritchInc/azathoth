"""Tests for run inspection command parsing and dispatch."""

from uuid import UUID

import pytest

import azathoth.cli.application as application
from azathoth.cli import (
    build_parser,
    main,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")


def test_workflow_runs_parser_records_identifier_without_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            "runs",
            str(WORKFLOW_ID),
        )
    )

    assert arguments.workflow_action == "runs"
    assert arguments.workflow_id == WORKFLOW_ID
    assert arguments.workflow_run_limit is None


def test_workflow_runs_parser_records_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            "runs",
            str(WORKFLOW_ID),
            "--limit",
            "3",
        )
    )

    assert arguments.workflow_run_limit == 3


@pytest.mark.parametrize(
    "limit",
    (
        "0",
        "-1",
        "many",
    ),
)
def test_workflow_runs_rejects_non_positive_limit(
    limit: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "runs",
                str(WORKFLOW_ID),
                "--limit",
                limit,
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "Expected a positive integer" in captured.err


def test_cli_dispatches_workflow_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[UUID, int | None]] = []

    def fake_list_workflow_runs(
        workflow_id: UUID,
        *,
        limit: int | None,
    ) -> int:
        calls.append(
            (
                workflow_id,
                limit,
            )
        )

        return 43

    monkeypatch.setattr(
        application,
        "list_workflow_runs",
        fake_list_workflow_runs,
    )

    result = main(
        (
            "workflow",
            "runs",
            str(WORKFLOW_ID),
            "--limit",
            "5",
        )
    )

    assert result == 43
    assert calls == [
        (
            WORKFLOW_ID,
            5,
        ),
    ]


def test_cli_workflow_help_lists_runs_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert ",runs}" in captured.out


def test_run_show_parser_records_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "run",
            "show",
            str(RUN_ID),
        )
    )

    assert arguments.command == "run"
    assert arguments.run_action == "show"
    assert arguments.run_id == RUN_ID


def test_cli_dispatches_run_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_ids: list[UUID] = []

    def fake_show_run(
        run_id: UUID,
    ) -> int:
        run_ids.append(run_id)

        return 47

    monkeypatch.setattr(
        application,
        "show_run",
        fake_show_run,
    )

    result = main(
        (
            "run",
            "show",
            str(RUN_ID),
        )
    )

    assert result == 47
    assert run_ids == [
        RUN_ID,
    ]


def test_cli_run_show_rejects_invalid_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "run",
                "show",
                "not-a-uuid",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "RUN_ID" in captured.err


def test_cli_run_without_action_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(("run",))

    captured = capsys.readouterr()

    assert result == 0
    assert "usage: azathoth" in captured.out


def test_cli_help_lists_run_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "{workflow,run," in captured.out
