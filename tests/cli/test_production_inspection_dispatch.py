"""Tests for production inspection command parsing and dispatch."""

from uuid import UUID

import pytest

import azathoth.cli.application as application
from azathoth.cli import (
    build_parser,
    main,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

INVOCATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-ccccccccccc1")


def test_workflow_production_parser_records_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            "production",
            str(WORKFLOW_ID),
        )
    )

    assert arguments.workflow_action == "production"
    assert arguments.workflow_id == WORKFLOW_ID


def test_cli_dispatches_workflow_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_ids: list[UUID] = []

    def fake_show_workflow_production(
        workflow_id: UUID,
    ) -> int:
        workflow_ids.append(workflow_id)

        return 71

    monkeypatch.setattr(
        application,
        "show_workflow_production",
        fake_show_workflow_production,
    )

    result = main(
        (
            "workflow",
            "production",
            str(WORKFLOW_ID),
        )
    )

    assert result == 71
    assert workflow_ids == [
        WORKFLOW_ID,
    ]


@pytest.mark.parametrize(
    ("action", "limit_attribute"),
    (
        ("revisions", "workflow_revision_limit"),
        ("invocations", "workflow_invocation_limit"),
    ),
)
def test_workflow_history_parsers_record_identifier_without_limit(
    action: str,
    limit_attribute: str,
) -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            action,
            str(WORKFLOW_ID),
        )
    )

    assert arguments.workflow_action == action
    assert arguments.workflow_id == WORKFLOW_ID
    assert getattr(arguments, limit_attribute) is None


@pytest.mark.parametrize(
    "action",
    (
        "revisions",
        "invocations",
    ),
)
@pytest.mark.parametrize(
    "limit",
    (
        "0",
        "-1",
        "many",
    ),
)
def test_workflow_history_parsers_reject_non_positive_limit(
    action: str,
    limit: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                action,
                str(WORKFLOW_ID),
                "--limit",
                limit,
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "Expected a positive integer" in captured.err


def test_cli_dispatches_workflow_revisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[UUID, int | None]] = []

    def fake_list_workflow_revisions(
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

        return 73

    monkeypatch.setattr(
        application,
        "list_workflow_revisions",
        fake_list_workflow_revisions,
    )

    result = main(
        (
            "workflow",
            "revisions",
            str(WORKFLOW_ID),
            "--limit",
            "4",
        )
    )

    assert result == 73
    assert calls == [
        (
            WORKFLOW_ID,
            4,
        ),
    ]


def test_cli_dispatches_workflow_invocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[UUID, int | None]] = []

    def fake_list_workflow_invocations(
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

        return 79

    monkeypatch.setattr(
        application,
        "list_workflow_invocations",
        fake_list_workflow_invocations,
    )

    result = main(
        (
            "workflow",
            "invocations",
            str(WORKFLOW_ID),
            "--limit",
            "6",
        )
    )

    assert result == 79
    assert calls == [
        (
            WORKFLOW_ID,
            6,
        ),
    ]


def test_cli_workflow_help_lists_production_inspection_actions(
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
    assert ",promote,production,revisions,invocations,experiments," in captured.out


def test_invocation_show_parser_records_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "invocation",
            "show",
            str(INVOCATION_ID),
        )
    )

    assert arguments.command == "invocation"
    assert arguments.invocation_action == "show"
    assert arguments.invocation_id == INVOCATION_ID


def test_cli_dispatches_invocation_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation_ids: list[UUID] = []

    def fake_show_invocation(
        invocation_id: UUID,
    ) -> int:
        invocation_ids.append(invocation_id)

        return 83

    monkeypatch.setattr(
        application,
        "show_invocation",
        fake_show_invocation,
    )

    result = main(
        (
            "invocation",
            "show",
            str(INVOCATION_ID),
        )
    )

    assert result == 83
    assert invocation_ids == [
        INVOCATION_ID,
    ]


def test_cli_invocation_show_rejects_invalid_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "invocation",
                "show",
                "not-a-uuid",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "INVOCATION_ID" in captured.err


def test_cli_invocation_without_action_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(("invocation",))

    captured = capsys.readouterr()

    assert result == 0
    assert "usage: azathoth" in captured.out


def test_cli_help_lists_invocation_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "{workflow,run,experiment,invocation,model," in captured.out
