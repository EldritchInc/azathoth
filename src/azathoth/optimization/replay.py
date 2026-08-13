"""Replay workflow optimization."""

from azathoth.optimization.workflow import (
    WorkflowOptimizationResult,
)
from azathoth.workflows.candidate import (
    WorkflowCandidate,
)
from azathoth.workflows.experiment import (
    WorkflowExperimentResult,
)


class ReplayWorkflowOptimizer:
    """Produce a new generation by replaying the existing population."""

    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult:
        """Return the supplied candidate population unchanged."""

        return WorkflowOptimizationResult(
            generation=generation,
            previous_experiment=experiment,
            candidates=candidates,
        )
