"""Orchestration services for running strategy experiments."""

from collections.abc import Sequence
from typing import Protocol

from azathoth.evaluation import Evaluator
from azathoth.optimization.models import (
    OptimizationExample,
    OptimizationRun,
    StrategyScorecard,
)
from azathoth.optimization.runner import OptimizationRunner
from azathoth.strategies import Strategy


class OptimizationRunService(Protocol):
    """A service capable of running one strategy against one example."""

    async def run(
        self,
        example: OptimizationExample,
        strategy: Strategy,
        evaluator: Evaluator,
    ) -> OptimizationRun:
        """Execute and evaluate one strategy against one example."""

        ...


class ExperimentRunner:
    """Run candidate strategies across a collection of examples."""

    def __init__(
        self,
        optimization_runner: OptimizationRunService | None = None,
    ) -> None:
        self._optimization_runner: OptimizationRunService = (
            optimization_runner if optimization_runner is not None else OptimizationRunner()
        )

    async def run(
        self,
        examples: Sequence[OptimizationExample],
        strategies: Sequence[Strategy],
        evaluator: Evaluator,
    ) -> tuple[StrategyScorecard, ...]:
        """Run every strategy against every example."""

        scorecards: list[StrategyScorecard] = []

        for strategy in strategies:
            runs: list[OptimizationRun] = []

            for example in examples:
                run = await self._optimization_runner.run(
                    example=example,
                    strategy=strategy,
                    evaluator=evaluator,
                )
                runs.append(run)

            if runs:
                scorecards.append(
                    StrategyScorecard(
                        strategy=strategy.metadata,
                        runs=tuple(runs),
                    )
                )

        return tuple(scorecards)
