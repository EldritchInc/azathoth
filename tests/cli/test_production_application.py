"""Tests for production workflow invocation CLI dispatch."""

from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.application as cli_application
from azathoth.cli import main

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_cli_workflow_invoke_dispatches_structured_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[
        tuple[
            UUID,
            JsonValue,
        ]
    ] = []

    def fake_invoke_workflow(
        *,
        workflow_id: UUID,
        payload: JsonValue,
    ) -> int:
        received.append(
            (
                workflow_id,
                payload,
            )
        )

        return 0

    monkeypatch.setattr(
        cli_application,
        "invoke_workflow",
        fake_invoke_workflow,
    )

    result = main(
        (
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            "--input",
            '{"message":"hello","count":3}',
        )
    )

    assert result == 0

    assert received == [
        (
            WORKFLOW_ID,
            {
                "message": "hello",
                "count": 3,
            },
        )
    ]


@pytest.mark.parametrize(
    "input_value, expected",
    (
        (
            '"hello"',
            "hello",
        ),
        (
            "42",
            42,
        ),
        (
            "true",
            True,
        ),
        (
            "null",
            None,
        ),
        (
            "[1,2,3]",
            [
                1,
                2,
                3,
            ],
        ),
    ),
)
def test_cli_workflow_invoke_accepts_any_json_value(
    monkeypatch: pytest.MonkeyPatch,
    input_value: str,
    expected: JsonValue,
) -> None:
    received: list[JsonValue] = []

    def fake_invoke_workflow(
        *,
        workflow_id: UUID,
        payload: JsonValue,
    ) -> int:
        assert workflow_id == WORKFLOW_ID

        received.append(
            payload,
        )

        return 0

    monkeypatch.setattr(
        cli_application,
        "invoke_workflow",
        fake_invoke_workflow,
    )

    result = main(
        (
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            "--input",
            input_value,
        )
    )

    assert result == 0
    assert received == [expected]


def test_cli_workflow_invoke_propagates_command_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_invoke_workflow(
        *,
        workflow_id: UUID,
        payload: JsonValue,
    ) -> int:
        assert workflow_id == WORKFLOW_ID
        assert payload == {}

        return 1

    monkeypatch.setattr(
        cli_application,
        "invoke_workflow",
        fake_invoke_workflow,
    )

    assert (
        main(
            (
                "workflow",
                "invoke",
                str(WORKFLOW_ID),
                "--input",
                "{}",
            )
        )
        == 1
    )


def test_cli_workflow_invoke_requires_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "invoke",
                str(WORKFLOW_ID),
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "--input" in captured.err


def test_cli_workflow_invoke_rejects_invalid_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "invoke",
                str(WORKFLOW_ID),
                "--input",
                "{definitely-not-json}",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "valid JSON" in captured.err


def test_cli_workflow_invoke_rejects_invalid_workflow_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "invoke",
                "definitely-not-a-uuid",
                "--input",
                "{}",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "invalid UUID value" in captured.err


def test_cli_workflow_help_includes_invoke(
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
    assert "invoke" in captured.out


def test_cli_workflow_invoke_help_describes_production_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "invoke",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "WORKFLOW_ID" in captured.out
    assert "--input" in captured.out
    assert "Production workflow input as JSON." in captured.out
