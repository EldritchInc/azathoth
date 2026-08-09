"""Workflow execution orchestration."""

from dataclasses import dataclass
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
    WorkflowStepStatus,
)
from azathoth.workflows.value import WorkflowValue


@dataclass(frozen=True)
class _LayerStepResult:
    """Temporary result produced while processing one workflow layer."""

    step: WorkflowCandidateStep
    step_context: Context | None
    execution: ExecutionResult | None


class WorkflowRunner:
    """Execute workflow candidates."""

    def __init__(
        self,
        *,
        executor: StrategyExecutor | None = None,
    ) -> None:
        self._executor = executor if executor is not None else StrategyExecutor()

    @staticmethod
    def _find_workflow_value(
        *,
        completed_steps: list[WorkflowStepRun],
        producer_step_id: UUID,
        name: str,
    ) -> WorkflowValue | None:
        """Return one previously committed workflow value."""

        matches = tuple(
            value
            for step_run in completed_steps
            if step_run.step_id == producer_step_id
            for value in step_run.values
            if value.name == name
        )

        if len(matches) > 1:
            raise RuntimeError(
                "Validated workflow value reference resolved more "
                "than one committed workflow value."
            )

        if not matches:
            return None

        return matches[0]

    @classmethod
    def _conditions_are_satisfied(
        cls,
        *,
        step: WorkflowCandidateStep,
        completed_steps: list[WorkflowStepRun],
    ) -> bool:
        """Return whether all conditions for a workflow step are satisfied."""

        for condition in step.conditions:
            value = cls._find_workflow_value(
                completed_steps=completed_steps,
                producer_step_id=condition.source.producer_step_id,
                name=condition.source.name,
            )

            if value is None:
                return False

            if value.value != condition.expected:
                return False

        return True

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

            if value is None:
                raise RuntimeError(
                    "Validated workflow input could not resolve a committed workflow value."
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

            layer_results: list[_LayerStepResult] = []

            for step in layer:
                if not self._conditions_are_satisfied(
                    step=step,
                    completed_steps=completed_steps,
                ):
                    layer_results.append(
                        _LayerStepResult(
                            step=step,
                            step_context=None,
                            execution=None,
                        )
                    )
                    continue

                step_context = self._build_step_context(
                    layer_context=layer_context,
                    step=step,
                    completed_steps=completed_steps,
                )

                execution = await self._executor.execute(
                    step.strategy,
                    step_context,
                )

                layer_results.append(
                    _LayerStepResult(
                        step=step,
                        step_context=step_context,
                        execution=execution,
                    )
                )

            for result in layer_results:
                if result.execution is None:
                    completed_steps.append(
                        WorkflowStepRun(
                            step_id=result.step.id,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.SKIPPED,
                            execution=None,
                            values=(),
                        )
                    )
                    continue

                if result.step_context is None:
                    raise RuntimeError("Executed workflow step is missing its step-start context.")

                execution = result.execution
                step_context = result.step_context

                current_context = self._merge_execution_context(
                    current_context=current_context,
                    execution_context=step_context,
                    execution=execution,
                )

                values = tuple(
                    WorkflowValue(
                        name=binding.name,
                        value=binding.resolve(execution.output),
                        producer_step_id=result.step.id,
                    )
                    for binding in result.step.outputs
                )

                completed_steps.append(
                    WorkflowStepRun(
                        step_id=result.step.id,
                        layer_index=layer_index,
                        status=WorkflowStepStatus.EXECUTED,
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
