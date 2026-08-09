"""Structured values produced by workflow execution."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkflowValue(BaseModel):
    """A structured value produced by a workflow step."""

    model_config = ConfigDict(
        frozen=True,
    )

    name: str

    value: Any

    producer_step_id: UUID
