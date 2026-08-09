"""Workflow execution orchestration."""

from datetime import UTC, datetime

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.workflows.candidate import WorkflowCandidate, WorkflowCandidateStep
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

    @staticmethod
    def _merge_execution_context(
        *,
        current_context: Context,
        layer_context: Context,
        execution: ExecutionResult,
    ) -> Context:
        """Append events produced by one layer execution."""

        if execution.initial_context != layer_context:
            raise RuntimeError(
                "Workflow step execution did not preserve the expected layer-start context."
            )

        initial_event_count = len(layer_context.events)

        produced_events = execution.final_context.events[initial_event_count:]

        merged = current_context

        for event in produced_events:
            merged = merged.append(event)

        return merged

    async def run(
        self,
        workflow: WorkflowCandidate,
        context: Context,
    ) -> WorkflowRun:
        """Execute a workflow candidate by dependency layer."""

        started_at = datetime.now(UTC)

        current_context = context
        completed_steps: list[WorkflowStepRun] = []

        for layer_index, layer in enumerate(workflow.execution_layers()):
            layer_context = current_context
            layer_executions: list[tuple[WorkflowCandidateStep, ExecutionResult]] = []

            for step in layer:
                execution = await self._executor.execute(
                    step.strategy,
                    layer_context,
                )

                layer_executions.append(
                    (
                        step,
                        execution,
                    )
                )

            for step, execution in layer_executions:
                current_context = self._merge_execution_context(
                    current_context=current_context,
                    layer_context=layer_context,
                    execution=execution,
                )

                completed_steps.append(
                    WorkflowStepRun(
                        step_id=step.id,
                        layer_index=layer_index,
                        execution=execution,
                        values=(),
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
