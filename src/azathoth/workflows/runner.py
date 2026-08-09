"""Workflow execution orchestration."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context, ContextEvent
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.workflows.candidate import (
    WorkflowCandidate,
    WorkflowCandidateStep,
)
from azathoth.workflows.execution import (
    WorkflowRun,
    WorkflowStepRun,
)
from azathoth.workflows.value import WorkflowValue


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
        execution_context: Context,
        execution: ExecutionResult,
    ) -> Context:
        """Append only events produced during strategy execution."""

        if execution.initial_context != execution_context:
            raise RuntimeError(
                "Workflow step execution did not preserve the expected step-start context."
            )

        initial_event_count = len(execution_context.events)

        produced_events = execution.final_context.events[initial_event_count:]

        merged = current_context

        for event in produced_events:
            merged = merged.append(event)

        return merged

    @staticmethod
    def _resolve_workflow_values(
        *,
        step: WorkflowCandidateStep,
        execution: ExecutionResult,
    ) -> tuple[WorkflowValue, ...]:
        """Resolve declared workflow values from a step execution."""

        return tuple(
            WorkflowValue(
                name=binding.name,
                value=binding.resolve(execution.output),
                producer_step_id=step.id,
            )
            for binding in step.outputs
        )

    @staticmethod
    def _find_workflow_value(
        *,
        completed_steps: list[WorkflowStepRun],
        producer_step_id: UUID,
        name: str,
    ) -> WorkflowValue:
        """Return a previously committed workflow value."""

        matches = tuple(
            value
            for step_run in completed_steps
            if step_run.step_id == producer_step_id
            for value in step_run.values
            if value.name == name
        )

        if len(matches) != 1:
            raise RuntimeError(
                "Validated workflow input could not resolve exactly one committed workflow value."
            )

        return matches[0]

    @classmethod
    def _build_step_context(
        cls,
        *,
        layer_context: Context,
        step: WorkflowCandidateStep,
        completed_steps: list[WorkflowStepRun],
    ) -> Context:
        """Add resolved workflow inputs to a step-local context."""

        step_context = layer_context

        for binding in step.inputs:
            value = cls._find_workflow_value(
                completed_steps=completed_steps,
                producer_step_id=binding.source.producer_step_id,
                name=binding.source.name,
            )

            step_context = step_context.append(
                ContextEvent(
                    event_type="workflow.input.bound",
                    payload={
                        "name": binding.name,
                        "value": value.value,
                        "producer_step_id": str(value.producer_step_id),
                        "source_name": value.name,
                    },
                    producer="workflow-runner",
                )
            )

        return step_context

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

            layer_executions: list[
                tuple[
                    WorkflowCandidateStep,
                    Context,
                    ExecutionResult,
                ]
            ] = []

            for step in layer:
                step_context = self._build_step_context(
                    layer_context=layer_context,
                    step=step,
                    completed_steps=completed_steps,
                )

                execution = await self._executor.execute(
                    step.strategy,
                    step_context,
                )

                layer_executions.append(
                    (
                        step,
                        step_context,
                        execution,
                    )
                )

            resolved_layer: list[
                tuple[
                    WorkflowCandidateStep,
                    Context,
                    ExecutionResult,
                    tuple[WorkflowValue, ...],
                ]
            ] = []

            for step, step_context, execution in layer_executions:
                values = self._resolve_workflow_values(
                    step=step,
                    execution=execution,
                )

                resolved_layer.append(
                    (
                        step,
                        step_context,
                        execution,
                        values,
                    )
                )

            for step, step_context, execution, values in resolved_layer:
                current_context = self._merge_execution_context(
                    current_context=current_context,
                    execution_context=step_context,
                    execution=execution,
                )

                completed_steps.append(
                    WorkflowStepRun(
                        step_id=step.id,
                        layer_index=layer_index,
                        execution=execution,
                        values=values,
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
