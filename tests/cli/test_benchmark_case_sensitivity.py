"""Tests that `benchmark add-case` labels the case it adds (ADR 0123)."""

from pathlib import Path

import pytest

from azathoth.cli import main
from azathoth.context import create_input_sensitivity_event
from azathoth.evaluation import SQLiteBenchmarkRepository
from azathoth.sensitivity import Sensitivity
from tests.cli.test_benchmark_add_case import (
    BENCHMARK_ID,
    added_case,
    configure,
    revisions,
)
from tests.workflows.test_benchmark_case_source import RUN_ID, create_run, input_event


def add_from_run(
    *options: str,
) -> int:
    return main(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--from-run",
            str(RUN_ID),
            "--comparison",
            "exact",
            "--expected",
            "4",
            *options,
        )
    )


def configure_labelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    label: Sensitivity,
) -> Path:
    """Save the benchmark and one run whose input was given a label."""

    return configure(
        monkeypatch,
        tmp_path,
        run=create_run(input_event(), create_input_sensitivity_event(label, producer="test")),
    )


def test_a_case_from_a_restricted_run_is_restricted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_labelled(monkeypatch, tmp_path, Sensitivity.RESTRICTED)

    assert add_from_run() == 0
    assert capsys.readouterr().err == ""
    assert added_case(database).sensitivity is Sensitivity.RESTRICTED

    dataset = SQLiteBenchmarkRepository(database).get(BENCHMARK_ID)

    assert dataset is not None
    assert dataset.sensitivity is Sensitivity.RESTRICTED


def test_a_case_from_an_unlabelled_run_is_unlabelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)

    assert add_from_run() == 0
    assert added_case(database).sensitivity is None


def test_a_case_may_be_labelled_more_sensitive_than_its_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = configure_labelled(monkeypatch, tmp_path, Sensitivity.PUBLIC)

    assert add_from_run("--sensitivity", "restricted") == 0
    assert added_case(database).sensitivity is Sensitivity.RESTRICTED


def test_a_case_labelled_lower_than_its_run_adds_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_labelled(monkeypatch, tmp_path, Sensitivity.RESTRICTED)

    assert add_from_run("--sensitivity", "public") == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (f"Run {RUN_ID} is restricted; a case made from it cannot be public.\n")
    assert revisions(database) == 1


def test_a_case_from_a_file_takes_the_label_given(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(monkeypatch, tmp_path)
    claim = tmp_path / "claim.txt"
    claim.write_text("Claim 412.", encoding="utf-8")

    status = main(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--input-file",
            str(claim),
            "--comparison",
            "exact",
            "--expected",
            "1",
            "--sensitivity",
            "restricted",
        )
    )

    assert status == 0, capsys.readouterr().err
    assert added_case(database).input == "Claim 412."
    assert added_case(database).sensitivity is Sensitivity.RESTRICTED


def test_an_unknown_label_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exited:
        add_from_run("--sensitivity", "secret")

    assert exited.value.code == 2
    assert "'secret' is not a sensitivity" in capsys.readouterr().err


def test_the_label_option_is_described_in_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(("benchmark", "add-case", "--help"))

    assert "--sensitivity LABEL" in capsys.readouterr().out


def test_the_documented_refusal_is_the_one_given(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_labelled(monkeypatch, tmp_path, Sensitivity.RESTRICTED)

    add_from_run("--sensitivity", "internal")

    refusal = capsys.readouterr().err.strip().replace(str(RUN_ID), "<RUN_ID>")
    readme = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"

    assert f"\n{refusal}\n" in readme.read_text(encoding="utf-8")
