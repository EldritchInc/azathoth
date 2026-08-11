"""Recorded results of executable workflow runs."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows.attempt import WorkflowStepAttempt
from azathoth.workflows.models import WorkflowMetadata
from azathoth.workflows.statistics import WorkflowRunStatistics
from azathoth.workflows.value import WorkflowValue


class WorkflowStepStatus(StrEnum):
    """The execution status of one workflow step."""

    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStepRun(BaseModel):
    """The recorded result of one workflow step."""

    model_config = ConfigDict(frozen=True)

    step_id: UUID
    layer_index: int = Field(ge=0)
    status: WorkflowStepStatus = WorkflowStepStatus.EXECUTED
    execution: ExecutionResult | None = None
    attempts: tuple[WorkflowStepAttempt, ...] = ()
    values: tuple[WorkflowValue, ...] = ()

    @model_validator(mode="after")
    def validate_execution_status(self) -> "WorkflowStepRun":
        """Ensure execution evidence matches the recorded step status."""

        if self.status is WorkflowStepStatus.EXECUTED:
            if self.execution is None:
                raise ValueError("Executed workflow steps must include an execution result.")

            if not self.attempts:
                raise ValueError(
                    "Executed workflow steps must include at least one execution attempt."
                )

            final_attempt = self.attempts[-1]

            if not final_attempt.succeeded:
                raise ValueError(
                    "Executed workflow steps must end with a successful execution attempt."
                )

            if final_attempt.execution != self.execution:
                raise ValueError(
                    "Executed workflow step result must match the final successful attempt."
                )

        if self.status is WorkflowStepStatus.FAILED:
            if self.execution is not None:
                raise ValueError(
                    "Failed workflow steps cannot include a successful execution result."
                )

            if not self.attempts:
                raise ValueError(
                    "Failed workflow steps must include at least one execution attempt."
                )

            if self.attempts[-1].succeeded:
                raise ValueError("Failed workflow steps must end with a failed execution attempt.")

            if self.values:
                raise ValueError("Failed workflow steps cannot produce workflow values.")

        if self.status is WorkflowStepStatus.SKIPPED:
            if self.execution is not None:
                raise ValueError("Skipped workflow steps cannot include an execution result.")

            if self.attempts:
                raise ValueError("Skipped workflow steps cannot include execution attempts.")

            if self.values:
                raise ValueError("Skipped workflow steps cannot produce workflow values.")

        return self


class WorkflowRun(BaseModel):
    """The complete recorded result of executing one workflow candidate."""

    model_config = ConfigDict(frozen=True)

    workflow: WorkflowMetadata
    steps: tuple[WorkflowStepRun, ...] = Field(min_length=1)

    initial_context: Context
    final_context: Context

    started_at: datetime
    completed_at: datetime

    @property
    def values(self) -> tuple[WorkflowValue, ...]:
        """Return all workflow values in recorded step order."""

        return tuple(value for step in self.steps for value in step.values)

    @property
    def statistics(self) -> WorkflowRunStatistics:
        """Return statistics derived from the recorded workflow execution."""

        executed_steps = sum(step.status is WorkflowStepStatus.EXECUTED for step in self.steps)
        failed_steps = sum(step.status is WorkflowStepStatus.FAILED for step in self.steps)
        skipped_steps = sum(step.status is WorkflowStepStatus.SKIPPED for step in self.steps)

        attempts = tuple(attempt for step in self.steps for attempt in step.attempts)

        successful_attempts = sum(attempt.succeeded for attempt in attempts)
        failed_attempts = len(attempts) - successful_attempts

        retry_count = sum(
            max(
                len(step.attempts) - 1,
                0,
            )
            for step in self.steps
        )

        duration_seconds = (self.completed_at - self.started_at).total_seconds()

        return WorkflowRunStatistics(
            total_steps=len(self.steps),
            executed_steps=executed_steps,
            failed_steps=failed_steps,
            skipped_steps=skipped_steps,
            total_attempts=len(attempts),
            successful_attempts=successful_attempts,
            failed_attempts=failed_attempts,
            retry_count=retry_count,
            duration_seconds=duration_seconds,
        )

    @property
    def succeeded(self) -> bool:
        """Return whether the workflow completed without failed steps."""

        return self.statistics.failed_steps == 0

    @property
    def failed(self) -> bool:
        """Return whether the workflow contains failed steps."""

        return not self.succeeded

    @property
    def duration_seconds(self) -> float:
        """Return the workflow execution duration in seconds."""

        return self.statistics.duration_seconds

    @property
    def retry_count(self) -> int:
        """Return the total retry count across the workflow."""

        return self.statistics.retry_count

    @property
    def executed_step_count(self) -> int:
        """Return the number of executed workflow steps."""

        return self.statistics.executed_steps

    @property
    def failed_step_count(self) -> int:
        """Return the number of failed workflow steps."""

        return self.statistics.failed_steps

    @property
    def skipped_step_count(self) -> int:
        """Return the number of skipped workflow steps."""

        return self.statistics.skipped_steps

    @property
    def total_attempt_count(self) -> int:
        """Return the total number of recorded execution attempts."""

        return self.statistics.total_attempts

    def values_named(
        self,
        name: str,
    ) -> tuple[WorkflowValue, ...]:
        """Return all workflow values with the supplied name."""

        return tuple(value for value in self.values if value.name == name)

    def values_from(
        self,
        producer_step_id: UUID,
    ) -> tuple[WorkflowValue, ...]:
        """Return all workflow values produced by one workflow step."""

        return tuple(value for value in self.values if value.producer_step_id == producer_step_id)

    @model_validator(mode="after")
    def validate_timestamps(self) -> "WorkflowRun":
        """Ensure workflow completion does not precede workflow start."""

        if self.completed_at < self.started_at:
            raise ValueError("Workflow completion time cannot precede its start time.")

        return self
