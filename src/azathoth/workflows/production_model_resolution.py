"""Resolve explicitly authorized models for production workflow steps."""

from uuid import UUID

from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    ContextPromptStrategySpec,
    FixedModelSelection,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
from azathoth.sensitivity import Sensitivity, may_receive
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
    portfolio: ModelPortfolio | None = None,
    sensitivity: Sensitivity | None = None,
) -> FixedModelSelection:
    """Resolve the first executable model explicitly authorized for a step.

    For an invocation labelled `sensitivity`, the first executable of the
    primary and its approved substitutes whose portfolio entry may receive
    input so labelled is resolved, if there is one (ADR 0123). Otherwise the
    primary is, when executable, and then the first executable substitute,
    so a restricted invocation with no such model is refused, saying why,
    when it sends. Only a context prompt step's choice depends on the label.
    """

    step = next(
        (step for step in state.specification.steps if step.id == step_id),
        None,
    )

    if step is None:
        raise ValueError(f"Workflow step {step_id} does not exist in production state.")

    specification = step.specification

    if not isinstance(
        specification,
        PROMPT_SPECIFICATIONS,
    ):
        raise ValueError(f"Workflow step {step_id} is not prompt-backed.")

    primary = specification.model_selection

    if not isinstance(
        primary,
        FixedModelSelection,
    ):
        raise ValueError("Production workflow prompt steps must use FixedModelSelection.")

    substitution = next(
        (
            substitution
            for substitution in state.model_substitutions
            if substitution.step_id == step_id
        ),
        None,
    )

    #
    # Only a context prompt shows a model the run's data; a fixed prompt's
    # text is its own, so its model is chosen as for any invocation.
    #
    label = sensitivity if isinstance(specification, ContextPromptStrategySpec) else None
    approved = (primary, *(() if substitution is None else substitution.substitutes))
    receiving = next(
        (
            selection
            for selection in approved
            if _receives(selection, portfolio=portfolio, sensitivity=label)
            and _is_executable(selection=selection, catalog=catalog, registry=registry)
        ),
        None,
    )

    if receiving is not None:
        return receiving

    if _is_executable(
        selection=primary,
        catalog=catalog,
        registry=registry,
    ):
        return primary

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


def _receives(
    selection: FixedModelSelection,
    *,
    portfolio: ModelPortfolio | None,
    sensitivity: Sensitivity | None,
) -> bool:
    """Return whether one model's portfolio entry may receive input with a label (ADR 0123)."""

    entry = None if portfolio is None else portfolio.get(selection.identifier)

    return may_receive(None if entry is None else entry.data_policy, sensitivity)


def _is_executable(
    *,
    selection: FixedModelSelection,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> bool:
    """Return whether one fixed model is both current and executable."""

    identifier = selection.identifier

    return catalog.get(identifier) is not None and registry.get(identifier) is not None
