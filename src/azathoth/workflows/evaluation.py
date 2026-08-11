"""Workflow evaluation models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from azathoth.workflows.reliability import (
    WorkflowReliabilityMetrics,
)
from azathoth.workflows.statistics import (
    WorkflowRunStatistics,
)


class WorkflowEvaluation(BaseModel):
    """Summarize a workflow execution for downstream evaluation."""

    model_config = ConfigDict(
        frozen=True,
    )

    workflow_id: UUID

    statistics: WorkflowRunStatistics

    reliability: WorkflowReliabilityMetrics

    evaluated_at: datetime
