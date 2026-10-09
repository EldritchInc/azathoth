"""Tests for durable evidence produced by workflow optimization."""

from pathlib import Path

import pytest

import azathoth.cli.workflows as workflow_commands
from azathoth.cli import (
    CliRuntimeConfiguration,
    optimize_workflow,
    render_workflow_optimization_session,
)
from azathoth.optimization import WorkflowOptimizationSession
from azathoth.workflows import (
    SQLiteWorkflowExperimentRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunEvaluationRepository,
    SQLiteWorkflowRunRepository,
)
from tests.cli.test_optimization_lifecycle import (
    WORKFLOW_ID,
    create_runtime,
    create_workflow,
)
from tests.cli.test_optimization_rendering import create_session


def optimize_with_database(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> WorkflowOptimizationSession:
    """Optimize one configured workflow against an isolated database."""

    workflow = create_workflow()

    SQLiteWorkflowRepository(database).save(workflow)

    configuration = CliRuntimeConfiguration(
        database=database,
    )

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: configuration,
    )

    runtime = create_runtime(
        workflow=workflow,
    )

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )

    sessions: list[WorkflowOptimizationSession] = []

    def capture_session(
        session: WorkflowOptimizationSession,
    ) -> str:
        sessions.append(session)

        return render_workflow_optimization_session(session)

    monkeypatch.setattr(
        workflow_commands,
        "render_workflow_optimization_session",
        capture_session,
    )

    result = optimize_workflow(
        workflow_id=WORKFLOW_ID,
        expected_value="success",
        target_latency_seconds=60.0,
        target_cost_usd=0.01,
        generations=2,
    )

    assert result == 0
    assert len(sessions) == 1

    return sessions[0]


def test_session_rendering_identifies_each_generation_experiment() -> None:
    session = create_session()

    lines = render_workflow_optimization_session(session).splitlines()

    for generation in session.generations:
        heading = lines.index(f"Generation {generation.generation}")

        assert lines[heading + 1] == f"Experiment ID: {generation.previous_experiment.id}"


def test_optimize_persists_one_experiment_record_per_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    session = optimize_with_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    captured = capsys.readouterr()

    experiment_ids = tuple(generation.previous_experiment.id for generation in session.generations)

    records = SQLiteWorkflowExperimentRepository(database).experiments()

    assert tuple(record.id for record in records) == experiment_ids

    for experiment_id in experiment_ids:
        assert f"Experiment ID: {experiment_id}\n" in captured.out


def test_optimize_persists_every_candidate_run_and_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"

    session = optimize_with_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    evaluated_candidates = sum(
        len(generation.previous_experiment.evidence) for generation in session.generations
    )

    runs = SQLiteWorkflowRunRepository(database).runs()
    evaluations = SQLiteWorkflowRunEvaluationRepository(database).evaluations()

    assert len(runs) == evaluated_candidates
    assert len(evaluations) == evaluated_candidates
    assert {evaluation.run_id for evaluation in evaluations} == {run.id for run in runs}


def test_optimize_experiment_records_reference_persisted_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"

    optimize_with_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    run_repository = SQLiteWorkflowRunRepository(database)
    evaluation_repository = SQLiteWorkflowRunEvaluationRepository(database)

    for record in SQLiteWorkflowExperimentRepository(database).experiments():
        for observation in record.observations:
            run = run_repository.get(observation.run_id)
            evaluation = evaluation_repository.get(observation.evaluation_id)

            assert run is not None
            assert run.workflow.id == WORKFLOW_ID
            assert evaluation is not None
            assert evaluation.run_id == observation.run_id
