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
from azathoth.workflows.failure import WorkflowFailurePolicy
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
        ExecutionResult | None,
        tuple[WorkflowStepAttempt, ...],
        Exception | None,
    ]:
        """Execute a strategy according to its retry policy."""

        attempts: list[WorkflowStepAttempt] = []

        for attempt_number in range(
            1,
            retry_policy.max_attempts + 1,
        ):
            started_at = datetime.now(
                tz=UTC,
            )

            try:
                execution = await self._executor.execute(
                    strategy,
                    context,
                )

                completed_at = datetime.now(
                    tz=UTC,
                )

                attempts.append(
                    WorkflowStepAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution=execution,
                    )
                )

                return (
                    execution,
                    tuple(attempts),
                    None,
                )

            except Exception as error:
                completed_at = datetime.now(
                    tz=UTC,
                )

                attempts.append(
                    WorkflowStepAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=completed_at,
                        failure=WorkflowStepFailure(
                            exception_type=type(error).__name__,
                            message=str(error),
                        ),
                    )
                )

                if attempt_number == retry_policy.max_attempts:
                    return (
                        None,
                        tuple(attempts),
                        error,
                    )

                retry_policy.delay_for_attempt(
                    attempt_number + 1,
                )

        raise AssertionError("Workflow retry execution completed without producing an outcome.")

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

        started_at = datetime.now(
            tz=UTC,
        )

        current_context = context
        completed_steps: list[WorkflowStepRun] = []

        blocked_step_ids: set[UUID] = set()

        for layer_index, layer in enumerate(workflow.execution_layers()):
            layer_context = current_context

            layer_results: list[
                tuple[
                    WorkflowCandidateStep,
                    Context | None,
                    ExecutionResult | None,
                    tuple[WorkflowStepAttempt, ...],
                    Exception | None,
                    WorkflowStepStatus,
                ]
            ] = []

            for step in layer:
                #
                # A dependency skipped because of SKIP_DEPENDENTS
                # blocks this step transitively.
                #
                if any(dependency_id in blocked_step_ids for dependency_id in step.depends_on):
                    blocked_step_ids.add(step.id)

                    layer_results.append(
                        (
                            step,
                            None,
                            None,
                            (),
                            None,
                            WorkflowStepStatus.SKIPPED,
                        )
                    )

                    continue

                #
                # Normal conditional eligibility.
                #
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
                            None,
                            WorkflowStepStatus.SKIPPED,
                        )
                    )

                    continue

                step_context = self._build_step_context(
                    layer_context=layer_context,
                    step=step,
                    completed_steps=completed_steps,
                )

                execution, attempts, error = await self._execute_with_retry(
                    strategy=step.strategy,
                    context=step_context,
                    retry_policy=step.retry_policy,
                )

                if error is not None:
                    if step.failure_policy is WorkflowFailurePolicy.FAIL_WORKFLOW:
                        raise error

                    if step.failure_policy is WorkflowFailurePolicy.SKIP_DEPENDENTS:
                        blocked_step_ids.add(step.id)

                    layer_results.append(
                        (
                            step,
                            step_context,
                            None,
                            attempts,
                            error,
                            WorkflowStepStatus.FAILED,
                        )
                    )

                    continue

                if execution is None:
                    raise RuntimeError(
                        "Successful workflow step execution did not produce an execution result."
                    )

                layer_results.append(
                    (
                        step,
                        step_context,
                        execution,
                        attempts,
                        None,
                        WorkflowStepStatus.EXECUTED,
                    )
                )

            #
            # Commit the layer in declared workflow order.
            #
            for (
                step,
                result_context,
                execution,
                attempts,
                error,
                status,
            ) in layer_results:
                if status is WorkflowStepStatus.SKIPPED:
                    completed_steps.append(
                        WorkflowStepRun(
                            step_id=step.id,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.SKIPPED,
                            execution=None,
                            attempts=(),
                            values=(),
                        )
                    )

                    continue

                if status is WorkflowStepStatus.FAILED:
                    if error is None:
                        raise RuntimeError("Failed workflow step is missing its failure.")

                    completed_steps.append(
                        WorkflowStepRun(
                            step_id=step.id,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.FAILED,
                            execution=None,
                            attempts=attempts,
                            values=(),
                        )
                    )

                    continue

                if execution is None:
                    raise RuntimeError("Executed workflow step is missing its execution result.")

                if result_context is None:
                    raise RuntimeError("Executed workflow step is missing its execution context.")

                current_context = self._merge_execution_context(
                    current_context=current_context,
                    execution_context=result_context,
                    execution=execution,
                )

                values = tuple(
                    WorkflowValue(
                        name=binding.name,
                        value=binding.resolve(execution.output),
                        producer_step_id=step.id,
                    )
                    for binding in step.outputs
                )

                completed_steps.append(
                    WorkflowStepRun(
                        step_id=step.id,
                        layer_index=layer_index,
                        status=WorkflowStepStatus.EXECUTED,
                        execution=execution,
                        attempts=attempts,
                        values=values,
                    )
                )
        completed_at = datetime.now(
            tz=UTC,
        )

        return WorkflowRun(
            workflow=workflow.metadata,
            steps=tuple(completed_steps),
            initial_context=context,
            final_context=current_context,
            started_at=started_at,
            completed_at=completed_at,
        )
