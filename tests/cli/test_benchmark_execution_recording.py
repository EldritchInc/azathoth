"""Tests for saving benchmark runs and comparisons from the CLI commands."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    compare_benchmarks,
    list_workflow_runs,
    run_benchmark,
)
from azathoth.evaluation import OutcomeComparison
from azathoth.workflows import (
    SQLiteWorkflowBenchmarkExecutionRepository,
    SQLiteWorkflowRunEvaluationRepository,
    SQLiteWorkflowRunRepository,
    WorkflowBenchmarkExecutionKind,
    WorkflowScoringPolicy,
)
from tests.cli.test_optimization import WORKFLOW_ID
from tests.cli.test_semantic_benchmark_commands import (
    BENCHMARK_ID,
    EXACT_CASE_ID,
    JUDGE_COST_USD,
    SECOND_WORKFLOW_ID,
    SEMANTIC_CASE_ID,
    configure,
    create_dataset,
    create_runtime,
)
from tests.evaluation.test_semantic import (
    PASS_REPLY,
    ScriptedJudgeModel,
)


def execution_id_from(
    output: str,
) -> UUID:
    """Return the execution identifier that leads one command's output."""

    first_line = output.splitlines()[0]

    assert first_line.startswith("Execution ID: ")

    return UUID(first_line.removeprefix("Execution ID: "))


def configure_run(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    judge: ScriptedJudgeModel,
) -> Path:
    """Configure one workflow, the semantic benchmark, and one judge."""

    return configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(judge),
        dataset=create_dataset(),
    )


def configure_comparison(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    judge: ScriptedJudgeModel,
) -> Path:
    """Configure two workflows, the semantic benchmark, and one judge."""

    return configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            judge,
            second_workflow=True,
        ),
        dataset=create_dataset(),
    )


def compare_both() -> int:
    """Compare both configured workflows on the semantic benchmark."""

    return compare_benchmarks(
        benchmark_id=BENCHMARK_ID,
        workflow_ids=(
            WORKFLOW_ID,
            SECOND_WORKFLOW_ID,
        ),
        target_latency_seconds=60.0,
        target_cost_usd=1.0,
    )


def test_benchmark_run_leads_with_its_saved_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_run(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        judge=ScriptedJudgeModel(
            PASS_REPLY,
            cost_usd=JUDGE_COST_USD,
        ),
    )

    status = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""

    execution_id = execution_id_from(captured.out)

    assert captured.out.startswith(
        f"Execution ID: {execution_id}\nBenchmark ID: {BENCHMARK_ID}\nWorkflow ID: {WORKFLOW_ID}\n"
    )

    record = SQLiteWorkflowBenchmarkExecutionRepository(database).get(execution_id)

    assert record is not None
    assert record.kind is WorkflowBenchmarkExecutionKind.RUN
    assert record.benchmark_id == BENCHMARK_ID
    assert record.case_ids == (
        EXACT_CASE_ID,
        SEMANTIC_CASE_ID,
    )

    (candidate,) = record.candidates

    assert candidate.workflow.id == WORKFLOW_ID
    assert candidate.cases_passed == 2
    assert candidate.judge_calls == 1
    assert candidate.judge_cost_usd == pytest.approx(JUDGE_COST_USD)


def test_benchmark_run_saves_every_case_run_and_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_run(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        judge=ScriptedJudgeModel(PASS_REPLY),
    )

    run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    record = SQLiteWorkflowBenchmarkExecutionRepository(database).get(
        execution_id_from(capsys.readouterr().out),
    )

    assert record is not None

    run_ids = tuple(case.run_id for case in record.candidates[0].cases)

    assert tuple(run.id for run in SQLiteWorkflowRunRepository(database).runs()) == run_ids

    evaluations = SQLiteWorkflowRunEvaluationRepository(database).evaluations()

    assert tuple(evaluation.run_id for evaluation in evaluations) == run_ids
    assert tuple(evaluation.id for evaluation in evaluations) == tuple(
        case.evaluation_id for case in record.candidates[0].cases
    )


def test_benchmark_run_saves_nothing_when_judging_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_run(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        judge=ScriptedJudgeModel(RuntimeError("down")),
    )

    status = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert SQLiteWorkflowBenchmarkExecutionRepository(database).executions() == ()
    assert SQLiteWorkflowRunRepository(database).runs() == ()


def test_benchmark_run_labels_its_runs_as_benchmark_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_run(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        judge=ScriptedJudgeModel(PASS_REPLY),
    )

    run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    capsys.readouterr()

    status = list_workflow_runs(WORKFLOW_ID)

    lines = capsys.readouterr().out.splitlines()

    assert status == 0
    assert len(lines) == 2
    assert all(line.split()[-2] == "benchmark" for line in lines)


def test_benchmark_compare_leads_with_its_saved_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_comparison(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        judge=ScriptedJudgeModel(
            PASS_REPLY,
            PASS_REPLY,
            cost_usd=JUDGE_COST_USD,
        ),
    )

    status = compare_both()

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""

    execution_id = execution_id_from(captured.out)

    assert captured.out.startswith(
        f"Execution ID: {execution_id}\nBenchmark ID: {BENCHMARK_ID}\n\nRank 1\n"
    )

    record = SQLiteWorkflowBenchmarkExecutionRepository(database).get(execution_id)

    assert record is not None
    assert record.kind is WorkflowBenchmarkExecutionKind.COMPARE
    assert record.scoring_policy == WorkflowScoringPolicy(
        target_latency_seconds=60.0,
        target_cost_usd=1.0,
    )
    assert {candidate.workflow.id for candidate in record.candidates} == {
        WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    }


def test_benchmark_compare_breaks_down_every_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_comparison(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        judge=ScriptedJudgeModel(
            PASS_REPLY,
            PASS_REPLY,
            cost_usd=JUDGE_COST_USD,
        ),
    )

    compare_both()

    output = capsys.readouterr().out

    assert (
        output.count(
            "Passed (exact): 1/1\n"
            "Passed (semantic): 1/1\n"
            "Run failures: 0\n"
            "Judge Calls: 1\n"
            "Judge Cost: $0.250000"
        )
        == 2
    )


def test_benchmark_compare_saves_every_case_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_comparison(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        judge=ScriptedJudgeModel(
            PASS_REPLY,
            PASS_REPLY,
        ),
    )

    compare_both()

    record = SQLiteWorkflowBenchmarkExecutionRepository(database).get(
        execution_id_from(capsys.readouterr().out),
    )

    assert record is not None

    run_ids = tuple(case.run_id for candidate in record.candidates for case in candidate.cases)

    assert len(run_ids) == 4
    assert tuple(run.id for run in SQLiteWorkflowRunRepository(database).runs()) == run_ids
    assert tuple(
        case.comparison for candidate in record.candidates for case in candidate.cases
    ) == (
        OutcomeComparison.EXACT,
        OutcomeComparison.SEMANTIC,
        OutcomeComparison.EXACT,
        OutcomeComparison.SEMANTIC,
    )


def test_benchmark_compare_saves_nothing_when_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            ScriptedJudgeModel(),
            judge_authorized=False,
            second_workflow=True,
        ),
        dataset=create_dataset(),
    )

    status = compare_both()

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert SQLiteWorkflowBenchmarkExecutionRepository(database).executions() == ()
    assert SQLiteWorkflowRunRepository(database).runs() == ()
