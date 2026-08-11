"""Workflow execution orchestration."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context, ContextEvent
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import Strategy
from azathoth.workflows.attempt import (
    WorkflowStepAttempt,
    WorkflowStepFailure,
)
from azathoth.workflows.candidate import (
    WorkflowCandidate,
    WorkflowCandidateStep,
)
from azathoth.workflows.execution import (
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
)
from azathoth.workflows.retry import WorkflowRetryPolicy
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

            if not condition.matches(value.value):
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

    async def _execute_with_retry(
        self,
        *,
        strategy: Strategy,
        context: Context,
        retry_policy: WorkflowRetryPolicy,
    ) -> tuple[
        ExecutionResult,
        tuple[WorkflowStepAttempt, ...],
    ]:
        """Execute a strategy according to its retry policy."""

        attempts: list[WorkflowStepAttempt] = []

        last_exception: Exception | None = None

        for attempt_number in range(
            1,
            retry_policy.max_attempts + 1,
        ):
            failure_started_at = datetime.now(
                tz=UTC,
            )

            try:
                execution = await self._executor.execute(
                    strategy,
                    context,
                )

                attempts.append(
                    WorkflowStepAttempt(
                        attempt_number=attempt_number,
                        started_at=execution.started_at,
                        completed_at=execution.completed_at,
                        execution=execution,
                    )
                )

                return (
                    execution,
                    tuple(attempts),
                )

            except Exception as error:
                failure_completed_at = datetime.now(
                    tz=UTC,
                )

                attempts.append(
                    WorkflowStepAttempt(
                        attempt_number=attempt_number,
                        started_at=failure_started_at,
                        completed_at=failure_completed_at,
                        failure=WorkflowStepFailure(
                            exception_type=type(error).__name__,
                            message=str(error),
                        ),
                    )
                )

                last_exception = error

                if attempt_number == retry_policy.max_attempts:
                    break

                retry_policy.delay_for_attempt(
                    attempt_number + 1,
                )

        assert last_exception is not None

        raise last_exception

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

            layer_results: list[
                tuple[
                    WorkflowCandidateStep,
                    Context | None,
                    ExecutionResult | None,
                    tuple[WorkflowStepAttempt, ...],
                ]
            ] = []

            for step in layer:
                if not self._conditions_are_satisfied(
                    step=step,
                    completed_steps=completed_steps,
                ):
                    layer_results.append(
                        (
                            step,
                            None,
                            None,
                            (),
                        )
                    )
                    continue

                step_context = self._build_step_context(
                    layer_context=layer_context,
                    step=step,
                    completed_steps=completed_steps,
                )

                execution, attempts = await self._execute_with_retry(
                    strategy=step.strategy,
                    context=step_context,
                    retry_policy=step.retry_policy,
                )

                layer_results.append(
                    (
                        step,
                        step_context,
                        execution,
                        attempts,
                    )
                )

            for (
                result_step,
                result_context,
                result_execution,
                result_attempts,
            ) in layer_results:
                if result_execution is None:
                    completed_steps.append(
                        WorkflowStepRun(
                            step_id=result_step.id,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.SKIPPED,
                            execution=None,
                            attempts=(),
                            values=(),
                        )
                    )
                    continue

                if result_context is None:
                    raise RuntimeError("Executed workflow step is missing its execution context.")

                current_context = self._merge_execution_context(
                    current_context=current_context,
                    execution_context=result_context,
                    execution=result_execution,
                )

                values = tuple(
                    WorkflowValue(
                        name=binding.name,
                        value=binding.resolve(result_execution.output),
                        producer_step_id=result_step.id,
                    )
                    for binding in result_step.outputs
                )

                completed_steps.append(
                    WorkflowStepRun(
                        step_id=result_step.id,
                        layer_index=layer_index,
                        status=WorkflowStepStatus.EXECUTED,
                        execution=result_execution,
                        attempts=result_attempts,
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
