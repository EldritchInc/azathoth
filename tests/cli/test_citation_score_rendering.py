"""Tests that a scorecard's citation score is rendered wherever its dimensions are (ADR 0117)."""

from collections.abc import Callable
from typing import Any

import pytest

import tests.cli.test_benchmark_execution_rendering as executions
import tests.cli.test_experiment_rendering as experiments
import tests.cli.test_optimization_rendering as optimizations
from azathoth.cli import (
    render_workflow_benchmark_comparison_execution,
    render_workflow_benchmark_execution,
    render_workflow_experiment,
    render_workflow_optimization_session,
)
from azathoth.workflows import WorkflowScorecard


def citing(
    create: Callable[..., WorkflowScorecard],
) -> Callable[..., WorkflowScorecard]:
    """Return a scorecard factory whose scorecards score their citations 0.5."""

    def created(
        *arguments: Any,
        **keywords: Any,
    ) -> WorkflowScorecard:
        return create(*arguments, **keywords).model_copy(update={"citation_score": 0.5})

    return created


@pytest.mark.parametrize(
    ("module", "render", "build", "line"),
    [
        pytest.param(
            executions,
            render_workflow_benchmark_comparison_execution,
            executions.create_comparison,
            "Cost: 0.800000\nCitations: 0.500000\nOverall: ",
            id="comparison",
        ),
        pytest.param(
            executions,
            render_workflow_benchmark_execution,
            executions.create_comparison,
            "Cost: 0.800000\nCitations: 0.500000\nOverall: ",
            id="execution",
        ),
        pytest.param(
            experiments,
            render_workflow_experiment,
            experiments.create_experiment,
            "Cost: 0.250000\nCitations: 0.500000\nOverall: ",
            id="experiment",
        ),
        pytest.param(
            optimizations,
            render_workflow_optimization_session,
            optimizations.create_session,
            "  Cost: 1.000000\n  Citations: 0.500000\n  Overall: ",
            id="optimization",
        ),
    ],
)
def test_a_citation_score_follows_the_cost_and_is_left_out_without_one(
    module: Any,
    render: Callable[[Any], str],
    build: Callable[[], Any],
    line: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "Citations: " not in render(build())

    monkeypatch.setattr(module, "create_scorecard", citing(module.create_scorecard))

    assert line in render(build())
