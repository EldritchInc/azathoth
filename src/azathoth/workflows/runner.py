"""Workflow execution orchestration."""

from datetime import UTC, datetime

from azathoth.context import Context
from azathoth.execution import StrategyExecutor
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.execution import (
    WorkflowRun,
    WorkflowStepRun,
)


class WorkflowRunner:
    """Execute workflow candidates."""

    def __init__(
        self,
        *,
        executor: StrategyExecutor | None = None,
    ) -> None:
        self._executor = executor if executor is not None else StrategyExecutor()

    async def run(
        self,
        workflow: WorkflowCandidate,
        context: Context,
    ) -> WorkflowRun:
        """Execute workflow candidate steps sequentially."""

        started_at = datetime.now(UTC)

        current_context = context
        completed_steps: list[WorkflowStepRun] = []

        for layer_index, step in enumerate(workflow.steps):
            execution = await self._executor.execute(
                step.strategy,
                current_context,
            )

            current_context = execution.final_context

            completed_steps.append(
                WorkflowStepRun(
                    step_id=step.id,
                    layer_index=layer_index,
                    execution=execution,
                )
            )

        completed_at = datetime.now(UTC)

        return WorkflowRun(
            workflow=workflow.metadata,
            steps=tuple(completed_steps),
            initial_context=context,
            final_context=current_context,
            started_at=started_at,
            completed_at=completed_at,
        )
