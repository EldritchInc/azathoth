"""Durable production state for workflows."""

from pydantic import BaseModel, ConfigDict

from azathoth.workflows.models import WorkflowSpecification


class WorkflowProductionState(BaseModel):
    """Represent the durable workflow configuration active in production."""

    model_config = ConfigDict(frozen=True)

    specification: WorkflowSpecification
