"""Durable production state for workflows."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.workflows.models import WorkflowSpecification


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class WorkflowProductionModelSubstitution(BaseModel):
    """Define explicitly approved fallback models for one production step."""

    model_config = ConfigDict(frozen=True)

    step_id: UUID
    substitutes: tuple[FixedModelSelection, ...] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_unique_substitutes(
        self,
    ) -> "WorkflowProductionModelSubstitution":
        """Require each fallback model to appear at most once."""

        identifiers = tuple(substitute.identifier for substitute in self.substitutes)

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Production model substitutes must be unique.")

        return self


class WorkflowProductionState(BaseModel):
    """Represent the durable workflow configuration active in production."""

    model_config = ConfigDict(frozen=True)

    specification: WorkflowSpecification
    model_substitutions: tuple[WorkflowProductionModelSubstitution, ...] = ()

    @model_validator(mode="after")
    def validate_production_configuration(
        self,
    ) -> "WorkflowProductionState":
        """Validate fixed production bindings and explicit substitutions."""

        primary_models: dict[
            UUID,
            FixedModelSelection,
        ] = {}

        for step in self.specification.steps:
            specification = step.specification

            if not isinstance(
                specification,
                PromptStrategySpec,
            ):
                continue

            model_selection = specification.model_selection

            if not isinstance(
                model_selection,
                FixedModelSelection,
            ):
                raise ValueError("Production workflow prompt steps must use FixedModelSelection.")

            primary_models[step.id] = model_selection

        substitution_step_ids = tuple(
            substitution.step_id for substitution in self.model_substitutions
        )

        if len(substitution_step_ids) != len(set(substitution_step_ids)):
            raise ValueError("Production model substitutions must reference unique workflow steps.")

        for substitution in self.model_substitutions:
            primary = primary_models.get(substitution.step_id)

            if primary is None:
                raise ValueError(
                    "Production model substitutions must reference prompt-backed workflow steps."
                )

            if any(
                substitute.identifier == primary.identifier
                for substitute in substitution.substitutes
            ):
                raise ValueError(
                    "Production model substitutes cannot include the step's primary model."
                )

        return self


class WorkflowProductionRevision(BaseModel):
    """Identify one immutable historical workflow production deployment."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    state: WorkflowProductionState
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def workflow_id(
        self,
    ) -> UUID:
        """Return the workflow identity represented by this production revision."""

        return self.state.specification.metadata.id
