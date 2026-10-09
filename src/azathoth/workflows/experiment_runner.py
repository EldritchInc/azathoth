"""Workflow experiment orchestration."""

from dataclasses import dataclass

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationResult,
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
from azathoth.workflows.experiment_record import (
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
)
from azathoth.workflows.experiment_recorder import (
    WorkflowExperimentEvidenceRecorder,
)
from azathoth.workflows.ranker import (
    WorkflowRanker,
)
from azathoth.workflows.run_evaluation import (
    WorkflowRunEvaluation,
)
from azathoth.workflows.runner import (
    WorkflowRunner,
)
from azathoth.workflows.scoring import (
    WorkflowScorer,
)


@dataclass(frozen=True)
class _ScoredExecution:
    """Keep one successful execution together with its evaluation."""

    run: WorkflowRun
    evaluation: EvaluationResult


class WorkflowExperimentRunner:
    """Execute, evaluate, score, and rank workflow candidates.

    When a recorder is supplied, every candidate run, every evaluation, and
    one experiment record are persisted as durable evidence. Without one, the
    runner keeps no evidence beyond the returned result.
    """

    def __init__(
        self,
        *,
        scorer: WorkflowScorer,
        runner: WorkflowRunner | None = None,
        ranker: WorkflowRanker | None = None,
        recorder: WorkflowExperimentEvidenceRecorder | None = None,
    ) -> None:
        self._runner = runner if runner is not None else WorkflowRunner()
        self._scorer = scorer
        self._ranker = ranker if ranker is not None else WorkflowRanker()
        self._recorder = recorder

    async def run(
        self,
        *,
        workflows: tuple[WorkflowCandidate, ...],
        context: Context,
        evaluator: Evaluator,
        expected_outcome: ExpectedOutcome,
    ) -> WorkflowExperimentResult:
        """Execute, evaluate, score, and rank successful workflow candidates."""

        evidence: list[WorkflowExperimentEvidence] = []
        executions: list[_ScoredExecution] = []

        for workflow in workflows:
            run = await self._runner.run_recording_failures(
                workflow=workflow,
                context=context,
            )

            if self._recorder is not None:
                self._recorder.runs.save(run)

            if run.failed:
                continue

            evaluation = await evaluator.evaluate(
                expected=expected_outcome,
                actual=self._output_from_run(run),
            )

            if self._recorder is not None:
                self._recorder.evaluations.save(
                    WorkflowRunEvaluation(
                        run_id=run.id,
                        evaluation=evaluation,
                    )
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
            executions.append(
                _ScoredExecution(
                    run=run,
                    evaluation=evaluation,
                )
            )

        if workflows and not evidence:
            raise ValueError("Workflow experiment produced no successful candidate executions.")

        scorecards = tuple(observation.scorecard for observation in evidence)

        ranking = self._ranker.rank(
            scorecards,
        )

        result = WorkflowExperimentResult(
            evidence=tuple(evidence),
            ranking=ranking,
        )

        if self._recorder is not None:
            self._recorder.experiments.save(
                self._record(
                    result=result,
                    executions=tuple(executions),
                )
            )

        return result

    @staticmethod
    def _record(
        *,
        result: WorkflowExperimentResult,
        executions: tuple[_ScoredExecution, ...],
    ) -> WorkflowExperimentRecord:
        """Build the durable record sharing the experiment result's identity.

        Observations keep candidate order. Ranking entries are matched to
        evidence positions the same way the result orders its evidence, so the
        record's run ranking agrees with the result's ranked evidence.
        """

        observations = tuple(
            WorkflowExperimentObservation(
                workflow=execution.run.workflow,
                candidate_signature=entry.candidate_signature,
                run_id=execution.run.id,
                evaluation_id=execution.evaluation.id,
                scorecard=entry.scorecard,
            )
            for entry, execution in zip(
                result.evidence,
                executions,
                strict=True,
            )
        )

        remaining = list(range(len(result.evidence)))
        ranking: list[int] = []

        for ranked in result.ranking.entries:
            position = next(
                index for index in remaining if result.evidence[index].scorecard == ranked.scorecard
            )

            remaining.remove(position)
            ranking.append(position)

        return WorkflowExperimentRecord(
            id=result.id,
            observations=observations,
            ranking=tuple(executions[index].run.id for index in ranking),
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
