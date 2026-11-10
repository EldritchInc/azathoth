"""Tests that show commands name a run's label, and warn when they print restricted data (ADR 0123).

The database holds a private Alpha, so restricted runs answer.
"""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli.rendering.benchmark_executions import (
    render_workflow_benchmark_comparison_execution,
    render_workflow_benchmark_execution,
)
from azathoth.cli.rendering.experiments import render_workflow_experiment
from azathoth.cli.rendering.sensitivity import (
    render_sensitivity_lines,
    restricted_output_warning,
    warn_if_restricted,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from tests.api.test_invoke import promote
from tests.cli.test_benchmark_execution_rendering import (
    create_comparison as create_comparison_execution,
)
from tests.cli.test_benchmark_execution_rendering import create_run as create_execution
from tests.cli.test_experiment_rendering import create_experiment
from tests.cli.test_restricted_execution import (
    PROVIDER,
    WORKFLOW_ID,
    imported,
    initialized,
    run,
)

BENCHMARK_ID = UUID("e7890000-0000-4000-8000-000000000001")

CASE_ID = UUID("e7890000-0000-4000-8000-000000000011")


def run_with(
    capsys: pytest.CaptureFixture[str],
    label: str | None,
    output: str = "jsonl",
) -> tuple[int, str, str]:
    """Run the workflow on a claim, labelled `label`, and return what the command printed."""

    options = () if label is None else ("--sensitivity", label)

    return run(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input",
        '"claim 412"',
        "--output",
        output,
        *options,
    )


def run_id(
    database: Path,
) -> UUID:
    (only,) = open_repositories(database).runs.runs()

    return only.id


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database whose portfolio holds a private Alpha."""

    return initialized(tmp_path, monkeypatch, capsys)


# The helper


def test_internal_data_names_no_label() -> None:
    assert render_sensitivity_lines(Sensitivity.INTERNAL) == ()
    assert render_sensitivity_lines(Sensitivity.PUBLIC) == ("Sensitivity: public",)
    assert render_sensitivity_lines(Sensitivity.RESTRICTED) == ("Sensitivity: restricted",)


def test_only_restricted_output_is_warned_of(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for label in Sensitivity:
        warn_if_restricted(label, "Run 1")

    captured = capsys.readouterr()

    assert (captured.out, captured.err) == (
        "",
        "Run 1 is restricted; its output contains restricted data.\n",
    )
    assert restricted_output_warning("Run 1") == (
        "Run 1 is restricted; its output contains restricted data."
    )


# Runs


@pytest.mark.parametrize("output", ["jsonl", "text", "result"])
def test_a_restricted_run_warns_that_its_output_is_restricted(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output: str,
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})

    status, _, err = run_with(capsys, "restricted", output)

    assert status == 0
    assert err.endswith(
        f"Run {run_id(database)} is restricted; its output contains restricted data.\n"
    )


@pytest.mark.parametrize("label", [None, "public", "internal"])
def test_other_runs_warn_of_nothing(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    label: str | None,
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})

    status, _, err = run_with(capsys, label)

    assert (status, err) == (0, "")


def test_run_show_names_the_label_and_warns(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})
    run_with(capsys, "restricted")

    identifier = run_id(database)
    status, out, err = run(capsys, "run", "show", str(identifier))

    assert status == 0
    assert f"Run ID: {identifier}\nSensitivity: restricted\n" in out
    assert err == f"Run {identifier} is restricted; its output contains restricted data.\n"


@pytest.mark.parametrize(("label", "line"), [("public", "Sensitivity: public\n"), (None, "")])
def test_run_show_names_another_label_only_when_it_is_not_internal(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    label: str | None,
    line: str,
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})
    run_with(capsys, label)

    identifier = run_id(database)
    status, out, err = run(capsys, "run", "show", str(identifier))

    assert (status, err) == (0, "")
    assert f"Run ID: {identifier}\n{line}Status:" in out


# Invocations


def invoked(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *options: str,
) -> tuple[int, str, str, UUID]:
    imported(tmp_path, capsys, {"provider": PROVIDER, "model": "alpha"})
    promote(str(database), WORKFLOW_ID)

    status, out, err = run(
        capsys,
        "workflow",
        "invoke",
        str(WORKFLOW_ID),
        "--input",
        '"claim 412"',
        *options,
    )
    (invocation,) = open_repositories(database).invocations.invocations()

    return status, out, err, invocation.id


def test_a_restricted_invocation_warns_and_its_show_names_its_label(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err, identifier = invoked(database, tmp_path, capsys, "--sensitivity", "restricted")
    warning = f"Invocation {identifier} is restricted; its output contains restricted data.\n"

    assert (status, err) == (0, warning)

    shown = run(capsys, "invocation", "show", str(identifier))

    assert shown[0] == 0
    assert shown[1].startswith(f"Invocation ID: {identifier}\nSensitivity: restricted\n")
    assert shown[2] == warning


def test_a_keyed_restricted_invocation_warns_too(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err, identifier = invoked(
        database,
        tmp_path,
        capsys,
        "--sensitivity",
        "restricted",
        "--idempotency-key",
        "claim-412",
    )

    assert (status, err) == (
        0,
        f"Invocation {identifier} is restricted; its output contains restricted data.\n",
    )


def test_an_unlabelled_invocation_warns_of_nothing(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err, identifier = invoked(database, tmp_path, capsys)

    assert (status, err) == (0, "")

    shown = run(capsys, "invocation", "show", str(identifier))

    assert shown[1].startswith(f"Invocation ID: {identifier}\nWorkflow ID:")
    assert shown[2] == ""


def test_a_restricted_job_warns_after_its_envelope(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"provider": PROVIDER, "model": "alpha"})
    promote(str(database), WORKFLOW_ID)

    request = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": "claim-412",
        "workflow_id": str(WORKFLOW_ID),
        "input": {"value": "claim 412", "sensitivity": "restricted"},
    }
    (tmp_path / "request.json").write_text(json.dumps(request), "utf-8")

    status, out, err = run(capsys, "job", "run", "request.json")
    (invocation,) = open_repositories(database).invocations.invocations()

    assert status == 0
    assert json.loads(out)["status"] == "succeeded"
    assert err == (
        f"Invocation {invocation.id} is restricted; its output contains restricted data.\n"
    )


# Benchmarks


def benchmark(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    label: Sensitivity | None,
) -> None:
    dataset = BenchmarkDataset(
        id=BENCHMARK_ID,
        name="claims",
        description="Claims.",
        cases=(
            BenchmarkCase(
                id=CASE_ID,
                input="claim 412",
                expected=ExpectedOutcome(
                    description="Alpha answers.",
                    value="alpha",
                    comparison=OutcomeComparison.EXACT,
                ),
                sensitivity=label,
            ),
        ),
    )
    (tmp_path / "benchmark.json").write_text(dataset.model_dump_json(), "utf-8")

    status, _, err = run(capsys, "benchmark", "import", "benchmark.json")

    assert status == 0, err


def test_a_restricted_benchmark_names_its_label_and_warns_when_its_cases_are_printed(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark(tmp_path, capsys, Sensitivity.RESTRICTED)

    shown = run(capsys, "benchmark", "show", str(BENCHMARK_ID))
    case = run(capsys, "benchmark", "case-show", str(BENCHMARK_ID), str(CASE_ID))
    exported = run(capsys, "benchmark", "export", str(BENCHMARK_ID))

    assert "\nCases: 1\nSensitivity: restricted\n" in shown[1]
    assert shown[2] == ""
    assert case[1].startswith(f"ID: {CASE_ID}\nSensitivity: restricted\n")
    assert case[2] == (
        f"Benchmark case {CASE_ID} is restricted; its output contains restricted data.\n"
    )
    assert exported[2] == (
        f"Benchmark {BENCHMARK_ID} is restricted; its output contains restricted data.\n"
    )


def test_an_unlabelled_benchmark_shows_and_warns_as_before(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark(tmp_path, capsys, None)

    shown = run(capsys, "benchmark", "show", str(BENCHMARK_ID))
    case = run(capsys, "benchmark", "case-show", str(BENCHMARK_ID), str(CASE_ID))
    exported = run(capsys, "benchmark", "export", str(BENCHMARK_ID))

    assert "Sensitivity" not in shown[1] + case[1]
    assert (shown[2], case[2], exported[2]) == ("", "", "")


# Executions and experiments


def test_executions_and_experiments_name_a_label_that_is_not_internal() -> None:
    execution = create_execution()
    comparison = create_comparison_execution()
    experiment = create_experiment()

    assert "Sensitivity" not in (
        render_workflow_benchmark_execution(execution)
        + render_workflow_benchmark_comparison_execution(comparison)
        + render_workflow_experiment(experiment)
    )

    restricted = {"sensitivity": Sensitivity.RESTRICTED}

    assert "\nSensitivity: restricted\nCandidates:" in render_workflow_benchmark_execution(
        execution.model_copy(update=restricted)
    )
    assert f"Benchmark ID: {comparison.benchmark_id}\nSensitivity: restricted\n" in (
        render_workflow_benchmark_comparison_execution(comparison.model_copy(update=restricted))
    )
    assert "\nSensitivity: restricted\nCandidates:" in render_workflow_experiment(
        experiment.model_copy(update=restricted)
    )


def test_the_documented_warnings_and_lines_are_the_ones_given() -> None:
    readme = (Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md").read_text(
        encoding="utf-8"
    )

    for subject in (
        "Run <RUN_ID>",
        "Invocation <INVOCATION_ID>",
        "Benchmark <BENCHMARK_ID>",
        "Benchmark case <CASE_ID>",
    ):
        assert f"\n{restricted_output_warning(subject)}\n" in readme

    (line,) = render_sensitivity_lines(Sensitivity.RESTRICTED)

    assert f"Run ID: <RUN_ID>\n{line}\n" in readme
