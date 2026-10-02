"""Aggregated reports describing where workflow resources are used."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.tools import ToolDefinition
from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.models import WorkflowMetadata, WorkflowSpecification
from azathoth.workflows.production import WorkflowProductionState
from azathoth.workflows.usage import (
    WorkflowHistoricalModelUsage,
    WorkflowHistoricalToolUsage,
    WorkflowProductionModelUsage,
    historical_model_usages,
    historical_tool_usages,
    production_model_usages,
    production_uses_tool,
    workflow_uses_model,
    workflow_uses_tool,
)


class WorkflowRunModelUsage(BaseModel):
    """Record successful executions of one model within one workflow run."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    started_at: datetime
    usages: tuple[WorkflowHistoricalModelUsage, ...] = Field(min_length=1)


class WorkflowModelUsageEntry(BaseModel):
    """Describe every known dependency of one workflow on one model."""

    model_config = ConfigDict(frozen=True)

    workflow: WorkflowMetadata
    configured: bool = False
    production: tuple[WorkflowProductionModelUsage, ...] = ()
    runs: tuple[WorkflowRunModelUsage, ...] = ()

    @model_validator(mode="after")
    def validate_has_usage(
        self,
    ) -> "WorkflowModelUsageEntry":
        """Require at least one configured, production, or historical usage."""

        if not self.configured and not self.production and not self.runs:
            raise ValueError("Workflow model usage entries must record at least one usage.")

        return self

    @property
    def in_production(self) -> bool:
        """Return whether active production depends on the model."""

        return bool(self.production)


class WorkflowModelUsageReport(BaseModel):
    """Describe where one exact model is configured, active, and executed."""

    model_config = ConfigDict(frozen=True)

    identifier: str = Field(min_length=1)
    workflows: tuple[WorkflowModelUsageEntry, ...] = ()

    @model_validator(mode="after")
    def validate_unique_workflows(
        self,
    ) -> "WorkflowModelUsageReport":
        """Require one entry per workflow identity."""

        workflow_ids = [entry.workflow.id for entry in self.workflows]

        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("Workflow model usage reports cannot contain duplicate workflows.")

        return self

    @property
    def used(self) -> bool:
        """Return whether any workflow depends on the model."""

        return bool(self.workflows)

    @property
    def production_workflows(self) -> tuple[WorkflowModelUsageEntry, ...]:
        """Return entries whose active production depends on the model."""

        return tuple(entry for entry in self.workflows if entry.in_production)

    @property
    def in_production(self) -> bool:
        """Return whether any active production depends on the model."""

        return bool(self.production_workflows)


class WorkflowRunToolUsage(BaseModel):
    """Record successful executions of one tool within one workflow run."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    started_at: datetime
    usages: tuple[WorkflowHistoricalToolUsage, ...] = Field(min_length=1)


class WorkflowToolUsageEntry(BaseModel):
    """Describe every known dependency of one workflow on one tool."""

    model_config = ConfigDict(frozen=True)

    workflow: WorkflowMetadata
    configured: bool = False
    production: bool = False
    runs: tuple[WorkflowRunToolUsage, ...] = ()

    @model_validator(mode="after")
    def validate_has_usage(
        self,
    ) -> "WorkflowToolUsageEntry":
        """Require at least one configured, production, or historical usage."""

        if not self.configured and not self.production and not self.runs:
            raise ValueError("Workflow tool usage entries must record at least one usage.")

        return self

    @property
    def in_production(self) -> bool:
        """Return whether active production requires the tool."""

        return self.production


class WorkflowToolUsageReport(BaseModel):
    """Describe where one durable tool identity is configured, active, and executed."""

    model_config = ConfigDict(frozen=True)

    tool_id: UUID
    tool_names: tuple[str, ...] = ()
    workflows: tuple[WorkflowToolUsageEntry, ...] = ()

    @model_validator(mode="after")
    def validate_unique_workflows(
        self,
    ) -> "WorkflowToolUsageReport":
        """Require one entry per workflow identity."""

        workflow_ids = [entry.workflow.id for entry in self.workflows]

        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("Workflow tool usage reports cannot contain duplicate workflows.")

        return self

    @property
    def used(self) -> bool:
        """Return whether any workflow depends on the tool."""

        return bool(self.workflows)

    @property
    def production_workflows(self) -> tuple[WorkflowToolUsageEntry, ...]:
        """Return entries whose active production requires the tool."""

        return tuple(entry for entry in self.workflows if entry.in_production)

    @property
    def in_production(self) -> bool:
        """Return whether any active production requires the tool."""

        return bool(self.production_workflows)


@dataclass
class _WorkflowModelUsageAccumulator:
    """Collect model usage for one workflow while a report is assembled."""

    workflow: WorkflowMetadata
    configured: bool = False
    production: list[WorkflowProductionModelUsage] = field(default_factory=list)
    runs: list[WorkflowRunModelUsage] = field(default_factory=list)

    def to_entry(self) -> WorkflowModelUsageEntry:
        """Freeze collected usage into one report entry."""

        return WorkflowModelUsageEntry(
            workflow=self.workflow,
            configured=self.configured,
            production=tuple(self.production),
            runs=tuple(self.runs),
        )


@dataclass
class _WorkflowToolUsageAccumulator:
    """Collect tool usage for one workflow while a report is assembled."""

    workflow: WorkflowMetadata
    configured: bool = False
    production: bool = False
    runs: list[WorkflowRunToolUsage] = field(default_factory=list)

    def to_entry(self) -> WorkflowToolUsageEntry:
        """Freeze collected usage into one report entry."""

        return WorkflowToolUsageEntry(
            workflow=self.workflow,
            configured=self.configured,
            production=self.production,
            runs=tuple(self.runs),
        )


def model_usage_report(
    identifier: str,
    *,
    specifications: Iterable[WorkflowSpecification],
    production_states: Iterable[WorkflowProductionState],
    runs: Iterable[WorkflowRun],
) -> WorkflowModelUsageReport:
    """Assemble configured, production, and historical usage of one exact model.

    Workflows appear in discovery order: configured specifications first, then
    production states, then run history. Metadata comes from the first source
    that discovered the workflow.
    """

    accumulators: dict[UUID, _WorkflowModelUsageAccumulator] = {}

    def accumulator_for(
        workflow: WorkflowMetadata,
    ) -> _WorkflowModelUsageAccumulator:
        accumulator = accumulators.get(workflow.id)

        if accumulator is None:
            accumulator = _WorkflowModelUsageAccumulator(
                workflow=workflow,
            )
            accumulators[workflow.id] = accumulator

        return accumulator

    for specification in specifications:
        if workflow_uses_model(
            specification,
            identifier,
        ):
            accumulator_for(specification.metadata).configured = True

    for state in production_states:
        production_usages = production_model_usages(
            state,
            identifier,
        )

        if production_usages:
            accumulator_for(state.specification.metadata).production.extend(
                production_usages,
            )

    for run in runs:
        historical_usages = historical_model_usages(
            run,
            identifier,
        )

        if historical_usages:
            accumulator_for(run.workflow).runs.append(
                WorkflowRunModelUsage(
                    run_id=run.id,
                    started_at=run.started_at,
                    usages=historical_usages,
                )
            )

    return WorkflowModelUsageReport(
        identifier=identifier,
        workflows=tuple(accumulator.to_entry() for accumulator in accumulators.values()),
    )


def tool_usage_report(
    tool_id: UUID,
    *,
    definitions: Iterable[ToolDefinition],
    specifications: Iterable[WorkflowSpecification],
    production_states: Iterable[WorkflowProductionState],
    runs: Iterable[WorkflowRun],
) -> WorkflowToolUsageReport:
    """Assemble configured, production, and historical usage of one tool identity.

    Workflows require tools by capability name, while execution history records
    the durable tool identity. Names are resolved from every definition version
    sharing the tool identity, so configured and production usage match any of
    them regardless of requirement version. History matches the identity alone.

    Workflows appear in discovery order: configured specifications first, then
    production states, then run history. Metadata comes from the first source
    that discovered the workflow.
    """

    tool_names = tuple(
        sorted({definition.name for definition in definitions if definition.id == tool_id})
    )

    accumulators: dict[UUID, _WorkflowToolUsageAccumulator] = {}

    def accumulator_for(
        workflow: WorkflowMetadata,
    ) -> _WorkflowToolUsageAccumulator:
        accumulator = accumulators.get(workflow.id)

        if accumulator is None:
            accumulator = _WorkflowToolUsageAccumulator(
                workflow=workflow,
            )
            accumulators[workflow.id] = accumulator

        return accumulator

    for specification in specifications:
        if any(
            workflow_uses_tool(
                specification,
                tool_name,
            )
            for tool_name in tool_names
        ):
            accumulator_for(specification.metadata).configured = True

    for state in production_states:
        if any(
            production_uses_tool(
                state,
                tool_name,
            )
            for tool_name in tool_names
        ):
            accumulator_for(state.specification.metadata).production = True

    for run in runs:
        historical_usages = historical_tool_usages(
            run,
            tool_id,
        )

        if historical_usages:
            accumulator_for(run.workflow).runs.append(
                WorkflowRunToolUsage(
                    run_id=run.id,
                    started_at=run.started_at,
                    usages=historical_usages,
                )
            )

    return WorkflowToolUsageReport(
        tool_id=tool_id,
        tool_names=tool_names,
        workflows=tuple(accumulator.to_entry() for accumulator in accumulators.values()),
    )


__all__ = [
    "WorkflowModelUsageEntry",
    "WorkflowModelUsageReport",
    "WorkflowRunModelUsage",
    "WorkflowRunToolUsage",
    "WorkflowToolUsageEntry",
    "WorkflowToolUsageReport",
    "model_usage_report",
    "tool_usage_report",
]
