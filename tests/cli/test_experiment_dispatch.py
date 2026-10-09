"""Tests for experiment inspection command parsing and dispatch."""

from uuid import UUID

import pytest

import azathoth.cli.application as application
from azathoth.cli import (
    build_parser,
    main,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555551")


def test_workflow_experiments_parser_records_identifier_without_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            "experiments",
            str(WORKFLOW_ID),
        )
    )

    assert arguments.workflow_action == "experiments"
    assert arguments.workflow_id == WORKFLOW_ID
    assert arguments.workflow_experiment_limit is None


@pytest.mark.parametrize(
    "limit",
    (
        "0",
        "-1",
        "many",
    ),
)
def test_workflow_experiments_rejects_non_positive_limit(
    limit: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "experiments",
                str(WORKFLOW_ID),
                "--limit",
                limit,
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "Expected a positive integer" in captured.err


def test_cli_dispatches_workflow_experiments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[UUID, int | None]] = []

    def fake_list_workflow_experiments(
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

        return 59

    monkeypatch.setattr(
        application,
        "list_workflow_experiments",
        fake_list_workflow_experiments,
    )

    result = main(
        (
            "workflow",
            "experiments",
            str(WORKFLOW_ID),
            "--limit",
            "3",
        )
    )

    assert result == 59
    assert calls == [
        (
            WORKFLOW_ID,
            3,
        ),
    ]


def test_cli_workflow_help_lists_experiments_action(
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
    assert ",experiments," in captured.out


def test_experiment_show_parser_records_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "experiment",
            "show",
            str(EXPERIMENT_ID),
        )
    )

    assert arguments.command == "experiment"
    assert arguments.experiment_action == "show"
    assert arguments.experiment_id == EXPERIMENT_ID


def test_cli_dispatches_experiment_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment_ids: list[UUID] = []

    def fake_show_experiment(
        experiment_id: UUID,
    ) -> int:
        experiment_ids.append(experiment_id)

        return 61

    monkeypatch.setattr(
        application,
        "show_experiment",
        fake_show_experiment,
    )

    result = main(
        (
            "experiment",
            "show",
            str(EXPERIMENT_ID),
        )
    )

    assert result == 61
    assert experiment_ids == [
        EXPERIMENT_ID,
    ]


def test_cli_experiment_show_rejects_invalid_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "experiment",
                "show",
                "not-a-uuid",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "EXPERIMENT_ID" in captured.err


def test_cli_experiment_without_action_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(("experiment",))

    captured = capsys.readouterr()

    assert result == 0
    assert "usage: azathoth" in captured.out


def test_cli_help_lists_experiment_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "{workflow,run,experiment," in captured.out
