"""Tests for rejecting benchmarks of workflows without declared results."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    compare_benchmarks,
    run_benchmark,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowMetadata,
)
from tests.cli.test_benchmark_comparison_commands import (
    FIRST_WORKFLOW_ID,
    SECOND_WORKFLOW_ID,
    forbid_runtime_bootstrap,
    persist,
)
from tests.cli.test_workflow_promotion_lifecycle import create_workflow
from tests.workflows.test_benchmark_comparisons import (
    DATASET_ID,
    create_mixed_dataset,
)


def save_workflow(
    database: Path,
    workflow_id: UUID,
    *,
    declares_result: bool,
) -> None:
    """Persist one configured workflow with or without a declared result."""

    workflow = create_workflow()

    SQLiteWorkflowRepository(database).save(
        workflow.model_copy(
            update={
                "metadata": WorkflowMetadata(
                    id=workflow_id,
                    name=f"workflow {workflow_id}",
                    description="Workflow used to test benchmark results.",
                    version="1.0.0",
                ),
                "result": workflow.result if declares_result else None,
            }
        )
    )


def test_benchmark_run_rejects_workflow_without_result_before_runtime_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persist(
        create_mixed_dataset(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    save_workflow(
        tmp_path / "azathoth.db",
        FIRST_WORKFLOW_ID,
        declares_result=False,
    )

    forbid_runtime_bootstrap(monkeypatch)

    result = run_benchmark(
        benchmark_id=DATASET_ID,
        workflow_id=FIRST_WORKFLOW_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {FIRST_WORKFLOW_ID} does not declare a result.\n"


def test_benchmark_compare_rejects_any_workflow_without_result_before_runtime_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persist(
        create_mixed_dataset(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    save_workflow(
        tmp_path / "azathoth.db",
        FIRST_WORKFLOW_ID,
        declares_result=True,
    )

    save_workflow(
        tmp_path / "azathoth.db",
        SECOND_WORKFLOW_ID,
        declares_result=False,
    )

    forbid_runtime_bootstrap(monkeypatch)

    result = compare_benchmarks(
        benchmark_id=DATASET_ID,
        workflow_ids=(FIRST_WORKFLOW_ID, SECOND_WORKFLOW_ID),
        target_latency_seconds=60.0,
        target_cost_usd=0.01,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {SECOND_WORKFLOW_ID} does not declare a result.\n"
