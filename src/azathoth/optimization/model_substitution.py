"""Generate workflow candidates using cheaper eligible language models."""

from dataclasses import replace

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategy,
    PromptStrategySpec,
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
) -> tuple[WorkflowCandidate, ...]:
    """Generate one-step substitutions using strictly cheaper eligible models."""

    if specification.metadata.id != candidate.metadata.id:
        raise ValueError("Workflow specification and candidate must share an identifier.")

    candidate_steps = {step.id: step for step in candidate.steps}

    substitutions: list[WorkflowCandidate] = []

    for workflow_step in specification.steps:
        prompt_specification = workflow_step.specification

        if not isinstance(
            prompt_specification,
            PromptStrategySpec,
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

        if not isinstance(
            strategy,
            PromptStrategy,
        ):
            raise ValueError("Prompt-backed workflow steps must use PromptStrategy candidates.")

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

            substitutions.append(
                _replace_prompt_step_model(
                    specification=prompt_specification,
                    candidate=candidate,
                    candidate_step=candidate_step,
                    target_model=target_model,
                    registry=registry,
                )
            )

    return tuple(substitutions)


def _replace_prompt_step_model(
    *,
    specification: PromptStrategySpec,
    candidate: WorkflowCandidate,
    candidate_step: WorkflowCandidateStep,
    target_model: ModelMetadata,
    registry: LanguageModelRegistry,
) -> WorkflowCandidate:
    """Return one candidate with a single prompt step rebound."""

    generated = generate_prompt_candidates(
        specification=specification,
        catalog=ModelCatalog(models=(target_model,)),
        registry=registry,
        portfolio=ModelPortfolio(
            entries=(
                ModelPortfolioEntry(
                    provider=target_model.provider,
                    model=target_model.model,
                ),
            )
        ),
    )

    if len(generated) != 1:
        raise RuntimeError(
            "Eligible executable model substitution did not generate exactly one prompt strategy."
        )

    replacement_step = replace(
        candidate_step,
        strategy=generated[0],
    )

    return WorkflowCandidate(
        metadata=candidate.metadata,
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
