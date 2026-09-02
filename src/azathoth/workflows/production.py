"""Durable production state for workflows."""

from pydantic import (
    BaseModel,
    ConfigDict,
    model_validator,
)

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.workflows.models import WorkflowSpecification


class WorkflowProductionState(BaseModel):
    """Represent the durable workflow configuration active in production."""

    model_config = ConfigDict(frozen=True)

    specification: WorkflowSpecification

    @model_validator(mode="after")
    def validate_fixed_prompt_models(
        self,
    ) -> "WorkflowProductionState":
        """Require every production prompt step to pin one exact model."""

        for step in self.specification.steps:
            specification = step.specification

            if not isinstance(
                specification,
                PromptStrategySpec,
            ):
                continue

            if not isinstance(
                specification.model_selection,
                FixedModelSelection,
            ):
                raise ValueError("Production workflow prompt steps must use FixedModelSelection.")

        return self
