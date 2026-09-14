"""Queries for discovering durable workflow dependencies."""

from collections.abc import Iterable

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.workflows.models import WorkflowSpecification


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


__all__ = [
    "workflow_uses_model",
    "workflows_using_model",
]
