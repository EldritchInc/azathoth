"""Tests for human-readable benchmark execution rendering."""

from types import SimpleNamespace
from uuid import UUID

from azathoth.cli import render_workflow_benchmark_result

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_result() -> SimpleNamespace:
    """Create deterministic aggregate benchmark evidence."""

    return SimpleNamespace(
        dataset_id=BENCHMARK_ID,
        cases_run=4,
        cases_passed=3,
        accuracy=0.75,
        total_tokens=120,
        total_latency_ms=875,
        total_cost_usd=0.001234,
    )


def test_benchmark_rendering_identifies_dataset_and_workflow() -> None:
    rendered = render_workflow_benchmark_result(
        create_result(),
        workflow_id=WORKFLOW_ID,
    )

    assert f"Benchmark ID: {BENCHMARK_ID}\n" in rendered
    assert f"Workflow ID: {WORKFLOW_ID}\n" in rendered


def test_benchmark_rendering_includes_evaluation_summary() -> None:
    rendered = render_workflow_benchmark_result(
        create_result(),
        workflow_id=WORKFLOW_ID,
    )

    assert "Cases Run: 4\n" in rendered
    assert "Cases Passed: 3\n" in rendered
    assert "Accuracy: 0.750000\n" in rendered


def test_benchmark_rendering_includes_execution_totals() -> None:
    rendered = render_workflow_benchmark_result(
        create_result(),
        workflow_id=WORKFLOW_ID,
    )

    assert "Total Tokens: 120\n" in rendered
    assert "Total Latency: 875 ms\n" in rendered
    assert "Total Cost: $0.001234" in rendered
