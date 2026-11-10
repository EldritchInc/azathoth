"""Generate workflow candidates using cheaper eligible language models."""

from dataclasses import replace

from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    PortfolioModelSelection,
    PromptSpecification,
    PromptStrategy,
    PromptStrategySpec,
    generate_context_prompt_candidates,
    generate_prompt_candidates,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelQuery,
    model_catalog_for_portfolio,
)
from azathoth.sensitivity import Sensitivity, may_receive
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowSpecification,
)


def generate_model_substitutions(
    *,
    specification: WorkflowSpecification,
    candidate: WorkflowCandidate,
    catalog: ModelCatalog,
    portfolio: ModelPortfolio,
    registry: LanguageModelRegistry,
    sensitivity: Sensitivity | None = None,
) -> tuple[WorkflowCandidate, ...]:
    """Generate one-step substitutions using strictly cheaper eligible models.

    Both fixed-prompt and context-prompt steps whose selection is a portfolio
    selection are substituted, one step at a time, in workflow step order.
    A substitute keeps its portfolio entry's declared data policy, and a
    context prompt step of runs labelled `sensitivity` is substituted only
    by models that may receive input so labelled (ADR 0123).
    """

    if specification.metadata.id != candidate.metadata.id:
        raise ValueError("Workflow specification and candidate must share an identifier.")

    candidate_steps = {step.id: step for step in candidate.steps}

    substitutions: list[WorkflowCandidate] = []

    for workflow_step in specification.steps:
        prompt_specification = workflow_step.specification

        if not isinstance(
            prompt_specification,
            PROMPT_SPECIFICATIONS,
        ):
            continue

        selection = prompt_specification.model_selection

        if not isinstance(
            selection,
            PortfolioModelSelection,
        ):
            continue

        candidate_step = candidate_steps[workflow_step.id]

        strategy = candidate_step.strategy

        if isinstance(prompt_specification, PromptStrategySpec):
            if not isinstance(strategy, PromptStrategy):
                raise ValueError("Prompt-backed workflow steps must use PromptStrategy candidates.")
        else:
            assert isinstance(prompt_specification, ContextPromptStrategySpec)

            if not isinstance(strategy, ContextPromptStrategy):
                raise ValueError(
                    "Context-prompt workflow steps must use ContextPromptStrategy candidates."
                )

        model_binding = strategy.model_binding

        if model_binding is None:
            raise ValueError("Prompt-backed workflow candidates must retain model bindings.")

        current_model = catalog.get(model_binding.identifier)

        if current_model is None:
            raise ValueError(
                "Workflow candidate model binding must reference the configured model catalog."
            )

        portfolio_catalog = model_catalog_for_portfolio(
            catalog=catalog,
            portfolio=portfolio,
        )

        eligible_models = portfolio_catalog.find(
            ModelQuery.from_requirements(selection.requirements)
        )

        for target_model in eligible_models:
            if target_model.identifier == current_model.identifier:
                continue

            if registry.get(target_model.identifier) is None:
                continue

            if not _is_strictly_cheaper(
                target=target_model,
                current=current_model,
            ):
                continue

            entry = portfolio.get(target_model.identifier)

            assert entry is not None

            if isinstance(prompt_specification, ContextPromptStrategySpec) and not may_receive(
                entry.data_policy,
                sensitivity,
            ):
                continue

            substitutions.append(
                _replace_prompt_step_model(
                    specification=prompt_specification,
                    candidate=candidate,
                    candidate_step=candidate_step,
                    target_model=target_model,
                    entry=entry,
                    registry=registry,
                )
            )

    return tuple(substitutions)


def _replace_prompt_step_model(
    *,
    specification: PromptSpecification,
    candidate: WorkflowCandidate,
    candidate_step: WorkflowCandidateStep,
    target_model: ModelMetadata,
    entry: ModelPortfolioEntry,
    registry: LanguageModelRegistry,
) -> WorkflowCandidate:
    """Return one candidate with a single prompt step rebound to an authorized model.

    Every other candidate attribute, including the declared result, is kept,
    and the rebound step holds the model's declared data policy.
    """

    catalog = ModelCatalog(models=(target_model,))
    portfolio = ModelPortfolio(entries=(entry,))

    generated: tuple[PromptStrategy, ...] | tuple[ContextPromptStrategy, ...]

    if isinstance(specification, PromptStrategySpec):
        generated = generate_prompt_candidates(
            specification=specification,
            catalog=catalog,
            registry=registry,
            portfolio=portfolio,
        )
    else:
        assert isinstance(specification, ContextPromptStrategySpec)

        generated = generate_context_prompt_candidates(
            specification=specification,
            catalog=catalog,
            registry=registry,
            portfolio=portfolio,
        )

    if len(generated) != 1:
        raise RuntimeError(
            "Eligible executable model substitution did not generate exactly one prompt strategy."
        )

    replacement_step = replace(
        candidate_step,
        strategy=generated[0],
    )

    return replace(
        candidate,
        steps=tuple(
            (replacement_step if step.id == candidate_step.id else step) for step in candidate.steps
        ),
    )


def _is_strictly_cheaper(
    *,
    target: ModelMetadata,
    current: ModelMetadata,
) -> bool:
    """Return whether target pricing strictly dominates current pricing."""

    if target.pricing is None:
        return False

    if current.pricing is None:
        return False

    target_input = target.pricing.input_usd_per_million_tokens
    target_output = target.pricing.output_usd_per_million_tokens

    current_input = current.pricing.input_usd_per_million_tokens
    current_output = current.pricing.output_usd_per_million_tokens

    no_more_expensive = target_input <= current_input and target_output <= current_output

    strictly_cheaper = target_input < current_input or target_output < current_output

    return no_more_expensive and strictly_cheaper
