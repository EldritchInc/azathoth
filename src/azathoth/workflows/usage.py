"""Queries for discovering durable workflow dependencies."""

from collections.abc import Iterable
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.production import WorkflowProductionState
from azathoth.workflows.steps import ToolStepSpecification


class WorkflowProductionModelUsageRole(StrEnum):
    """Describe how one model participates in production."""

    PRIMARY = "primary"
    SUBSTITUTE = "substitute"


class WorkflowProductionModelUsage(BaseModel):
    """Record one production model dependency."""

    model_config = ConfigDict(frozen=True)

    step_id: UUID
    role: WorkflowProductionModelUsageRole


def workflow_uses_model(
    specification: WorkflowSpecification,
    model_identifier: str,
) -> bool:
    """Return whether a workflow explicitly configures one exact model."""

    for step in specification.steps:
        step_specification = step.specification

        if not isinstance(
            step_specification,
            (
                PromptStrategySpec,
                ContextPromptStrategySpec,
            ),
        ):
            continue

        model_selection = step_specification.model_selection

        if not isinstance(
            model_selection,
            FixedModelSelection,
        ):
            continue

        if model_selection.identifier == model_identifier:
            return True

    return False


def workflows_using_model(
    specifications: Iterable[WorkflowSpecification],
    model_identifier: str,
) -> tuple[WorkflowSpecification, ...]:
    """Return workflows explicitly configured to use one exact model."""

    return tuple(
        specification
        for specification in specifications
        if workflow_uses_model(
            specification,
            model_identifier,
        )
    )


def workflow_uses_tool(
    specification: WorkflowSpecification,
    tool_name: str,
) -> bool:
    """Return whether a workflow requires one durable tool capability."""

    for step in specification.steps:
        step_specification = step.specification

        if not isinstance(
            step_specification,
            ToolStepSpecification,
        ):
            continue

        if step_specification.requirement.name == tool_name:
            return True

    return False


def workflows_using_tool(
    specifications: Iterable[WorkflowSpecification],
    tool_name: str,
) -> tuple[WorkflowSpecification, ...]:
    """Return workflows requiring one durable tool capability."""

    return tuple(
        specification
        for specification in specifications
        if workflow_uses_tool(
            specification,
            tool_name,
        )
    )


def production_model_usages(
    state: WorkflowProductionState,
    model_identifier: str,
) -> tuple[WorkflowProductionModelUsage, ...]:
    """Return production roles held by one exact model."""

    substitutions_by_step = {
        substitution.step_id: substitution for substitution in state.model_substitutions
    }

    usages: list[WorkflowProductionModelUsage] = []

    for step in state.specification.steps:
        step_specification = step.specification

        if isinstance(
            step_specification,
            (
                PromptStrategySpec,
                ContextPromptStrategySpec,
            ),
        ):
            model_selection = step_specification.model_selection

            if (
                isinstance(
                    model_selection,
                    FixedModelSelection,
                )
                and model_selection.identifier == model_identifier
            ):
                usages.append(
                    WorkflowProductionModelUsage(
                        step_id=step.id,
                        role=WorkflowProductionModelUsageRole.PRIMARY,
                    )
                )

        substitution = substitutions_by_step.get(
            step.id,
        )

        if substitution is None:
            continue

        if any(candidate.identifier == model_identifier for candidate in substitution.substitutes):
            usages.append(
                WorkflowProductionModelUsage(
                    step_id=step.id,
                    role=WorkflowProductionModelUsageRole.SUBSTITUTE,
                )
            )

    return tuple(usages)


def production_uses_tool(
    state: WorkflowProductionState,
    tool_name: str,
) -> bool:
    """Return whether active production requires one tool capability."""

    return workflow_uses_tool(
        state.specification,
        tool_name,
    )


__all__ = [
    "WorkflowProductionModelUsage",
    "WorkflowProductionModelUsageRole",
    "production_model_usages",
    "production_uses_tool",
    "workflow_uses_model",
    "workflow_uses_tool",
    "workflows_using_model",
    "workflows_using_tool",
]
