"""Queries for discovering durable workflow dependencies."""

from collections.abc import Iterable

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.steps import ToolStepSpecification


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


__all__ = [
    "workflow_uses_model",
    "workflow_uses_tool",
    "workflows_using_model",
    "workflows_using_tool",
]
