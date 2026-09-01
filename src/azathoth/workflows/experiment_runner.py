"""Workflow experiment orchestration."""

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.evaluation import (
    Evaluator,
    ExpectedOutcome,
)
from azathoth.workflows.candidate import (
    WorkflowCandidate,
)
from azathoth.workflows.execution import (
    WorkflowRun,
)
from azathoth.workflows.experiment import (
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
)
from azathoth.workflows.ranker import (
    WorkflowRanker,
)
from azathoth.workflows.runner import (
    WorkflowRunner,
)
from azathoth.workflows.scoring import (
    WorkflowScorer,
)


class WorkflowExperimentRunner:
    """Execute, evaluate, score, and rank workflow candidates."""

    def __init__(
        self,
        *,
        scorer: WorkflowScorer,
        runner: WorkflowRunner | None = None,
        ranker: WorkflowRanker | None = None,
    ) -> None:
        self._runner = runner if runner is not None else WorkflowRunner()
        self._scorer = scorer
        self._ranker = ranker if ranker is not None else WorkflowRanker()

    async def run(
        self,
        *,
        workflows: tuple[WorkflowCandidate, ...],
        context: Context,
        evaluator: Evaluator,
        expected_outcome: ExpectedOutcome,
    ) -> WorkflowExperimentResult:
        """Execute, evaluate, score, and rank workflow candidates."""

        evidence: list[WorkflowExperimentEvidence] = []

        for workflow in workflows:
            run = await self._runner.run(
                workflow=workflow,
                context=context,
            )

            evaluation = await evaluator.evaluate(
                expected=expected_outcome,
                actual=self._output_from_run(run),
            )

            scorecard = self._scorer.score(
                run=run,
                evaluation=evaluation,
            )

            evidence.append(
                WorkflowExperimentEvidence(
                    candidate_signature=workflow.signature,
                    scorecard=scorecard,
                )
            )

        scorecards = tuple(observation.scorecard for observation in evidence)

        ranking = self._ranker.rank(
            scorecards,
        )

        return WorkflowExperimentResult(
            evidence=tuple(evidence),
            ranking=ranking,
        )

    @staticmethod
    def _output_from_run(
        run: WorkflowRun,
    ) -> JsonValue:
        """Return the last successfully executed workflow step output."""

        for step in reversed(run.steps):
            if step.execution is not None:
                return step.execution.output

        raise ValueError(
            "Workflow experiment cannot evaluate a run without a successful step execution."
        )
