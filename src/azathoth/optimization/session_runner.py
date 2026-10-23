"""Workflow optimization session orchestration."""

from typing import Protocol

from azathoth.evaluation import BenchmarkDataset
from azathoth.optimization.session import WorkflowOptimizationSession
from azathoth.optimization.workflow import WorkflowOptimizer
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.experiment import WorkflowExperimentResult


class WorkflowExperimentService(Protocol):
    """Run experiments over workflow candidate populations."""

    async def run(
        self,
        *,
        workflows: tuple[WorkflowCandidate, ...],
        dataset: BenchmarkDataset,
    ) -> WorkflowExperimentResult:
        """Execute and compare one workflow candidate population on a benchmark."""

        ...


class WorkflowOptimizationSessionRunner:
    """Run iterative workflow optimization sessions."""

    def __init__(
        self,
        *,
        experiment_runner: WorkflowExperimentService,
        optimizer: WorkflowOptimizer,
    ) -> None:
        self._experiment_runner = experiment_runner
        self._optimizer = optimizer

    async def run(
        self,
        *,
        initial_candidates: tuple[WorkflowCandidate, ...],
        dataset: BenchmarkDataset,
        max_generations: int,
    ) -> WorkflowOptimizationSession:
        """Run workflow experiments and optimization for multiple generations.

        Every generation's candidates are judged against every case of the
        same benchmark dataset.

        Raises:
            ValueError: Fewer than one generation was requested.
        """

        if max_generations < 1:
            raise ValueError("Workflow optimization sessions require at least one generation.")

        current_candidates = initial_candidates
        generations = []

        for generation in range(1, max_generations + 1):
            experiment = await self._experiment_runner.run(
                workflows=current_candidates,
                dataset=dataset,
            )

            result = self._optimizer.optimize(
                experiment=experiment,
                candidates=current_candidates,
                generation=generation,
            )

            generations.append(result)

            current_candidates = tuple(result.candidates)

        return WorkflowOptimizationSession(
            initial_candidates=initial_candidates,
            generations=tuple(generations),
        )
