"""Resolve explicitly authorized models for production workflow steps."""

from uuid import UUID

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.workflows.production import WorkflowProductionState


class ProductionModelResolutionError(RuntimeError):
    """Base error raised when a production model cannot be resolved."""


class ProductionPrimaryModelUnavailableError(ProductionModelResolutionError):
    """Raised when an unavailable primary has no approved substitutes."""


class ProductionModelSubstitutesUnavailableError(ProductionModelResolutionError):
    """Raised when no explicitly approved production model is executable."""


def resolve_production_model_selection(
    *,
    state: WorkflowProductionState,
    step_id: UUID,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> FixedModelSelection:
    """Resolve the first executable model explicitly authorized for a step."""

    step = next(
        (step for step in state.specification.steps if step.id == step_id),
        None,
    )

    if step is None:
        raise ValueError(f"Workflow step {step_id} does not exist in production state.")

    specification = step.specification

    if not isinstance(
        specification,
        PromptStrategySpec,
    ):
        raise ValueError(f"Workflow step {step_id} is not prompt-backed.")

    primary = specification.model_selection

    if not isinstance(
        primary,
        FixedModelSelection,
    ):
        raise ValueError("Production workflow prompt steps must use FixedModelSelection.")

    if _is_executable(
        selection=primary,
        catalog=catalog,
        registry=registry,
    ):
        return primary

    substitution = next(
        (
            substitution
            for substitution in state.model_substitutions
            if substitution.step_id == step_id
        ),
        None,
    )

    if substitution is None:
        raise ProductionPrimaryModelUnavailableError(
            f"Production primary model {primary.identifier!r} "
            f"is unavailable for workflow step {step_id}."
        )

    for substitute in substitution.substitutes:
        if _is_executable(
            selection=substitute,
            catalog=catalog,
            registry=registry,
        ):
            return substitute

    raise ProductionModelSubstitutesUnavailableError(
        f"No approved production model substitute is available for workflow step {step_id}."
    )


def _is_executable(
    *,
    selection: FixedModelSelection,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> bool:
    """Return whether one fixed model is both current and executable."""

    identifier = selection.identifier

    return catalog.get(identifier) is not None and registry.get(identifier) is not None
