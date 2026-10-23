"""Tests for naming the exact benchmark revision in saved evidence."""

import asyncio
import json
from pathlib import Path

import pytest

from azathoth.cli import (
    compare_configured_benchmarks,
    execute_configured_benchmark,
    list_benchmark_history,
    render_workflow_benchmark_execution,
    render_workflow_experiment,
    run_benchmark,
    show_benchmark_execution,
)
from azathoth.evaluation import InMemoryBenchmarkRepository
from azathoth.revisions import content_digest
from azathoth.workflows import (
    InMemoryWorkflowBenchmarkExecutionRepository,
    InMemoryWorkflowExperimentRepository,
    InMemoryWorkflowRunEvaluationRepository,
    InMemoryWorkflowRunRepository,
    WorkflowBenchmarkEvidenceRecorder,
    WorkflowBenchmarkExecutionRecord,
    WorkflowExperimentEvidenceRecorder,
    WorkflowExperimentRecord,
    WorkflowExperimentRunner,
    WorkflowScorer,
    WorkflowScoringPolicy,
)
from tests.cli.test_benchmark_comparison import (
    CORRECT_WORKFLOW_ID,
    INCORRECT_WORKFLOW_ID,
)
from tests.cli.test_benchmark_comparison import (
    create_dataset as create_comparison_dataset,
)
from tests.cli.test_benchmark_comparison import (
    create_runtime as create_comparison_runtime,
)
from tests.cli.test_benchmark_execution import (
    WORKFLOW_ID,
    create_dataset,
)
from tests.cli.test_benchmark_execution_recording import (
    configure_run,
    execution_id_from,
)
from tests.cli.test_benchmark_execution_rendering import create_run
from tests.cli.test_experiment_rendering import create_experiment
from tests.cli.test_optimization import WORKFLOW_ID as COMMAND_WORKFLOW_ID
from tests.cli.test_semantic_benchmark_commands import BENCHMARK_ID
from tests.evaluation.test_semantic import (
    PASS_REPLY,
    ScriptedJudgeModel,
)
from tests.workflows.test_workflow_revision_lineage import (
    create_catalog,
    create_runtime,
)

POLICY = WorkflowScoringPolicy(
    target_latency_seconds=5.0,
    target_cost_usd=0.01,
)


def create_benchmark_recorder() -> WorkflowBenchmarkEvidenceRecorder:
    """Create a benchmark recorder over empty in-memory repositories."""

    return WorkflowBenchmarkEvidenceRecorder(
        runs=InMemoryWorkflowRunRepository(),
        evaluations=InMemoryWorkflowRunEvaluationRepository(),
        executions=InMemoryWorkflowBenchmarkExecutionRepository(),
    )


def without_key(
    payload: str,
    key: str,
) -> str:
    """Return a JSON document with one top-level key removed."""

    document = json.loads(payload)

    del document[key]

    return json.dumps(document)


def test_benchmark_results_name_the_dataset_content() -> None:
    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(create_catalog()),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
        )
    )

    assert result.dataset_digest == content_digest(create_dataset())


def test_recorded_runs_match_the_imported_benchmark_revision() -> None:
    benchmarks = InMemoryBenchmarkRepository()

    imported = benchmarks.save(create_dataset())

    recorder = create_benchmark_recorder()

    asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(create_catalog()),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
            recorder=recorder,
        )
    )

    (execution,) = recorder.executions.executions()

    assert execution.benchmark_digest == imported.content_digest


def test_recorded_comparisons_name_the_dataset_content() -> None:
    recorder = create_benchmark_recorder()

    asyncio.run(
        compare_configured_benchmarks(
            runtime=create_comparison_runtime(),
            workflow_ids=(
                CORRECT_WORKFLOW_ID,
                INCORRECT_WORKFLOW_ID,
            ),
            dataset=create_comparison_dataset(),
            scoring_policy=POLICY,
            recorder=recorder,
        )
    )

    (execution,) = recorder.executions.executions()

    assert execution.benchmark_digest == content_digest(create_comparison_dataset())


def test_recorded_experiments_name_the_dataset_content() -> None:
    recorder = WorkflowExperimentEvidenceRecorder(
        runs=InMemoryWorkflowRunRepository(),
        evaluations=InMemoryWorkflowRunEvaluationRepository(),
        experiments=InMemoryWorkflowExperimentRepository(),
    )

    candidate = create_comparison_runtime().generate_workflow_candidate(CORRECT_WORKFLOW_ID)

    asyncio.run(
        WorkflowExperimentRunner(
            scorer=WorkflowScorer(
                policy=POLICY,
            ),
            recorder=recorder,
        ).run(
            workflows=(candidate,),
            dataset=create_comparison_dataset(),
        )
    )

    (experiment,) = recorder.experiments.experiments()

    assert experiment.benchmark_digest == content_digest(create_comparison_dataset())


def test_records_written_before_digests_decode_without_one() -> None:
    execution = create_run().model_copy(
        update={
            "benchmark_digest": "a" * 64,
        },
    )

    decoded_execution = WorkflowBenchmarkExecutionRecord.model_validate_json(
        without_key(
            execution.model_dump_json(),
            "benchmark_digest",
        )
    )

    experiment = create_experiment().model_copy(
        update={
            "benchmark_digest": "b" * 64,
        },
    )

    decoded_experiment = WorkflowExperimentRecord.model_validate_json(
        without_key(
            experiment.model_dump_json(),
            "benchmark_digest",
        )
    )

    assert decoded_execution.benchmark_digest is None
    assert decoded_experiment.benchmark_digest is None


def test_records_reject_malformed_digests() -> None:
    with pytest.raises(ValueError):
        WorkflowBenchmarkExecutionRecord.model_validate_json(
            create_run()
            .model_copy(
                update={
                    "benchmark_digest": "not-a-digest",
                },
            )
            .model_dump_json()
        )


def test_execution_and_experiment_rendering_name_the_digest() -> None:
    execution = create_run().model_copy(
        update={
            "benchmark_digest": "c" * 64,
        },
    )

    experiment = create_experiment().model_copy(
        update={
            "benchmark_digest": "d" * 64,
        },
    )

    assert "\nBenchmark Digest: cccccccccccc\n" in render_workflow_benchmark_execution(execution)
    assert "\nBenchmark Digest: dddddddddddd\n" in render_workflow_experiment(experiment)


def test_execution_show_matches_benchmark_history(
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
        workflow_id=COMMAND_WORKFLOW_ID,
    )

    execution_id = execution_id_from(capsys.readouterr().out)

    list_benchmark_history(BENCHMARK_ID)

    (history_line,) = capsys.readouterr().out.splitlines()

    short_digest = history_line.split()[2]

    show_benchmark_execution(execution_id)

    assert f"\nBenchmark Digest: {short_digest}\n" in capsys.readouterr().out
