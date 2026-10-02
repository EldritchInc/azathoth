"""Tests for run feedback command parsing and dispatch."""

from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.application as application
from azathoth.cli import (
    build_parser,
    main,
)
from azathoth.workflows import WorkflowRunFeedbackDisposition

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")


def capture_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[UUID, WorkflowRunFeedbackDisposition, str | None, JsonValue]]:
    """Replace feedback recording with a recorder of dispatched calls."""

    calls: list[tuple[UUID, WorkflowRunFeedbackDisposition, str | None, JsonValue]] = []

    def fake_record_run_feedback(
        run_id: UUID,
        *,
        disposition: WorkflowRunFeedbackDisposition,
        reason: str | None,
        corrected_output: JsonValue,
    ) -> int:
        calls.append(
            (
                run_id,
                disposition,
                reason,
                corrected_output,
            )
        )

        return 53

    monkeypatch.setattr(
        application,
        "record_run_feedback",
        fake_record_run_feedback,
    )

    return calls


def test_run_feedback_parser_records_good_judgment() -> None:
    arguments = build_parser().parse_args(
        (
            "run",
            "feedback",
            str(RUN_ID),
            "--good",
        )
    )

    assert arguments.run_action == "feedback"
    assert arguments.run_id == RUN_ID
    assert arguments.run_feedback_disposition == "good"
    assert arguments.run_feedback_reason is None
    assert arguments.run_feedback_corrected_output is None


def test_cli_dispatches_good_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = capture_feedback(monkeypatch)

    result = main(
        (
            "run",
            "feedback",
            str(RUN_ID),
            "--good",
            "--reason",
            "Exactly right.",
        )
    )

    assert result == 53
    assert calls == [
        (
            RUN_ID,
            WorkflowRunFeedbackDisposition.GOOD,
            "Exactly right.",
            None,
        ),
    ]


def test_cli_dispatches_bad_feedback_with_corrected_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = capture_feedback(monkeypatch)

    result = main(
        (
            "run",
            "feedback",
            str(RUN_ID),
            "--bad",
            "--reason",
            "Wrong label.",
            "--corrected-output",
            '{"classification":"negative"}',
        )
    )

    assert result == 53
    assert calls == [
        (
            RUN_ID,
            WorkflowRunFeedbackDisposition.BAD,
            "Wrong label.",
            {
                "classification": "negative",
            },
        ),
    ]


def test_run_feedback_requires_a_disposition(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "run",
                "feedback",
                str(RUN_ID),
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "--good" in captured.err
    assert "--bad" in captured.err


def test_run_feedback_rejects_both_dispositions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "run",
                "feedback",
                str(RUN_ID),
                "--good",
                "--bad",
                "--reason",
                "Undecided.",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "not allowed with argument" in captured.err


def test_run_feedback_rejects_invalid_corrected_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "run",
                "feedback",
                str(RUN_ID),
                "--bad",
                "--reason",
                "Wrong label.",
                "--corrected-output",
                "{not json",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "valid JSON" in captured.err


def test_cli_run_help_lists_feedback_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "run",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "{show,feedback}" in captured.out
