"""Tests that restricted CLI runs, invocations and benchmarks prompt only allowed models (ADR 0123).

Two models answer with their own names. Beta comes first in the portfolio
and declares nothing; Alpha is declared private.
"""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import main
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.resumption import resume_configured_workflow
from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.inputs import ResolvedInput
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolioEntry,
)
from azathoth.revisions import AUTHOR_VARIABLE
from azathoth.sensitivity import PRIVATE_DATA_POLICY, Sensitivity
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from azathoth.workflows import (
    WorkflowRunner,
    create_production_invocation,
    create_workflow_input_events,
)
from tests.api.test_invoke import promote
from tests.workflows.test_run_resume import Crash, CrashingJournal

PROVIDER = "provider-a"

ALPHA = f"{PROVIDER}/alpha"

BETA = f"{PROVIDER}/beta"

WORKFLOW_ID = UUID("e1230000-0000-4000-8000-000000000001")

STEP_ID = UUID("e1230000-0000-4000-8000-000000000011")

BENCHMARK_ID = UUID("e1230000-0000-4000-8000-000000000021")


def workflow(
    model_selection: dict[str, Any],
) -> dict[str, Any]:
    """Return a one-step workflow whose context prompt shows a model the run's input."""

    return {
        "metadata": {
            "id": str(WORKFLOW_ID),
            "name": "answer",
            "description": "Answer the request.",
            "version": "1.0.0",
        },
        "steps": [
            {
                "id": str(STEP_ID),
                "specification": {
                    "metadata": {
                        "id": str(UUID(int=STEP_ID.int + 1)),
                        "name": "answer",
                        "description": "Answer the request.",
                        "version": "1.0.0",
                    },
                    "template": {
                        "text": "Answer: {request}",
                        "bindings": [
                            {
                                "variable_name": "request",
                                "event_type": "workflow.input.received",
                                "field_name": "input",
                            }
                        ],
                    },
                    "model_selection": model_selection,
                },
                "outputs": [{"name": "answer", "path": []}],
                "retry_policy": {"max_attempts": 1},
            }
        ],
        "result": {"name": "answer"},
    }


def run(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one CLI command; return its status, output and errors."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database whose portfolio holds Beta, then a private Alpha."""

    return initialized(tmp_path, monkeypatch, capsys)


def initialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database whose portfolio holds Beta, then a private Alpha; return it."""

    path = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(path))
    monkeypatch.setenv(AUTHOR_VARIABLE, "Eris")
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(
            models=tuple(
                ModelMetadata(provider=PROVIDER, model=name, display_name=name)
                for name in ("alpha", "beta")
            )
        ),
    )
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(
            {
                f"{PROVIDER}/{name}": DeterministicLanguageModel(
                    provider=PROVIDER,
                    model=name,
                    response_text=name,
                )
                for name in ("alpha", "beta")
            }
        ),
    )

    status, _, err = run(capsys, "init")

    assert status == 0, err

    portfolio = open_repositories(path).portfolio
    portfolio.save(ModelPortfolioEntry(provider=PROVIDER, model="beta"))
    portfolio.save(
        ModelPortfolioEntry(provider=PROVIDER, model="alpha", data_policy=PRIVATE_DATA_POLICY)
    )

    return path


def imported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    model_selection: dict[str, Any],
) -> None:
    (tmp_path / "workflow.json").write_text(json.dumps(workflow(model_selection)), "utf-8")

    status, _, err = run(capsys, "workflow", "import", "workflow.json")

    assert status == 0, err


def result_of(
    out: str,
) -> object:
    record = json.loads(out.strip().splitlines()[-1])

    return record.get("value", record)


# Runs


def test_a_restricted_run_is_answered_by_the_private_model(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})

    unlabelled = run(capsys, "workflow", "run", str(WORKFLOW_ID), "--input", '"claim 412"')
    restricted = run(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input",
        '"claim 412"',
        "--sensitivity",
        "restricted",
    )

    assert (unlabelled[0], result_of(unlabelled[1])) == (0, "beta")
    assert (restricted[0], result_of(restricted[1])) == (0, "alpha")


def test_a_restricted_run_on_an_undeclared_model_sends_nothing(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"provider": PROVIDER, "model": "beta"})

    status, out, _ = run(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input",
        '"claim 412"',
        "--sensitivity",
        "restricted",
        "--output",
        "text",
    )

    assert status == 1
    assert f"Step {STEP_ID} sent nothing. {BETA} cannot receive restricted input" in out


# Invocations


def test_a_restricted_invocation_waits_for_its_model_to_be_declared_private(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"provider": PROVIDER, "model": "beta"})
    promote(str(database), WORKFLOW_ID)

    def invoke() -> tuple[int, str, str]:
        return run(
            capsys,
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            "--input",
            '"claim 412"',
            "--sensitivity",
            "restricted",
        )

    refused = invoke()

    status, _, err = run(capsys, "model", "policy", BETA, "--no-retention", "--no-training")

    assert status == 0, err

    answered = invoke()

    assert refused[0] == 1
    assert (answered[0], result_of(answered[1])) == (0, {"result": "beta"})


# Benchmarks


def test_a_restricted_benchmark_runs_its_cases_on_the_private_model(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})

    dataset = BenchmarkDataset(
        id=BENCHMARK_ID,
        name="claims",
        description="Claims.",
        cases=(
            BenchmarkCase(
                input="claim 412",
                expected=ExpectedOutcome(
                    description="Alpha answers.",
                    value="alpha",
                    comparison=OutcomeComparison.EXACT,
                ),
                sensitivity=Sensitivity.RESTRICTED,
            ),
        ),
    )
    (tmp_path / "benchmark.json").write_text(dataset.model_dump_json(), "utf-8")

    for arguments in (
        ("benchmark", "import", "benchmark.json"),
        ("benchmark", "run", str(BENCHMARK_ID), "--workflow", str(WORKFLOW_ID)),
    ):
        status, _, err = run(capsys, *arguments)

        assert status == 0, err

    (execution,) = open_repositories(database).benchmark_executions.executions()
    (candidate,) = execution.candidates
    (case,) = candidate.cases

    assert case.passed
    assert execution.sensitivity is Sensitivity.RESTRICTED


def test_a_restricted_benchmark_refuses_an_undeclared_judge_before_any_case_runs(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})

    dataset = BenchmarkDataset(
        id=BENCHMARK_ID,
        name="claims",
        description="Claims.",
        cases=(
            BenchmarkCase(
                input="claim 412",
                expected=ExpectedOutcome(
                    description="Alpha answers.",
                    value="alpha",
                    comparison=OutcomeComparison.SEMANTIC,
                ),
                sensitivity=Sensitivity.RESTRICTED,
            ),
        ),
    )
    (tmp_path / "benchmark.json").write_text(dataset.model_dump_json(), "utf-8")

    for arguments in (("benchmark", "import", "benchmark.json"), ("judge", "add", BETA)):
        status, _, err = run(capsys, *arguments)

        assert status == 0, err

    judged: tuple[tuple[str, ...], ...] = (
        ("benchmark", "run", str(BENCHMARK_ID), "--workflow", str(WORKFLOW_ID)),
        (
            "workflow",
            "optimize",
            str(WORKFLOW_ID),
            "--benchmark",
            str(BENCHMARK_ID),
            "--target-latency",
            "5",
            "--target-cost",
            "0.01",
        ),
    )

    for command in judged:
        status, _, err = run(capsys, *command)

        assert status == 1
        assert f"Judge model {BETA} cannot receive restricted input" in err

    assert open_repositories(database).runs.runs() == ()


# Resuming


def test_a_resumed_restricted_invocation_reads_the_portfolio(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"provider": PROVIDER, "model": "alpha"})
    promote(str(database), WORKFLOW_ID)

    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="claim 412",
        sensitivity=Sensitivity.RESTRICTED,
    )
    open_repositories(database).invocations.save(invocation)

    status, out, err = run(capsys, "invocation", "resume", str(invocation.id))

    assert status == 0, err
    assert result_of(out) == {"result": "alpha"}
    assert err == (
        f"Invocation {invocation.id} is restricted; its output contains restricted data.\n"
    )


def test_a_resumed_restricted_run_keeps_to_the_private_model(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported(tmp_path, capsys, {"requirements": {}})

    stores = open_repositories(database)
    journal = CrashingJournal()
    journal.crash("attempt.finished")
    runtime = load_runtime(CliRuntimeConfiguration.from_environment())
    context = Context(
        events=create_workflow_input_events(
            ResolvedInput(
                value="claim 412",
                media_type="application/json",
                sensitivity=Sensitivity.RESTRICTED,
            ),
            producer="test",
        )
    )

    with pytest.raises(Crash):
        asyncio.run(
            WorkflowRunner(journal=journal).run_recording_failures(
                runtime.generate_workflow_candidate(
                    WORKFLOW_ID, sensitivity=Sensitivity.RESTRICTED
                ),
                context,
            )
        )

    (run_id,) = journal.run_ids

    resumed, _ = asyncio.run(
        resume_configured_workflow(
            runtime=runtime,
            run_id=run_id,
            entries=journal.entries(run_id),
            specifications=stores.workflows,
            runner=WorkflowRunner(journal=journal),
        )
    )

    assert not resumed.failed
    assert resumed.final_context.events[-1].payload["strategy_name"] == f"answer [{ALPHA}]"
