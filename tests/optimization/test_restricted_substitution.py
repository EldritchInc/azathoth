"""Tests that restricted optimization substitutes only models that may receive it (ADR 0123)."""

import asyncio
from uuid import UUID

import tests.cli.test_optimization as optimization
from azathoth.cli import optimize_configured_workflow
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.optimization import generate_model_substitutions
from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    PortfolioModelSelection,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import ModelPortfolio, ModelPortfolioEntry, ModelRequirements
from azathoth.runtime import AzathothRuntime
from azathoth.sensitivity import PRIVATE_DATA_POLICY, UNKNOWN_DATA_POLICY, Sensitivity
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)
from tests.optimization.test_context_model_substitution import (
    bound_models,
    create_workflow,
    expensive_candidate,
    summary_step,
    triage_step,
)
from tests.optimization.test_model_substitution import (
    CHEAPER_IDENTIFIER,
    CHEAPEST_IDENTIFIER,
    create_catalog,
    create_registry,
)

OPTIMIZED_WORKFLOW_ID = UUID("e4560000-0000-4000-8000-000000000001")

OPTIMIZED_STEP_ID = UUID("e4560000-0000-4000-8000-000000000011")

OPTIMIZED_STRATEGY_ID = UUID("e4560000-0000-4000-8000-000000000021")


def portfolio(
    *private: str,
) -> ModelPortfolio:
    """Authorize every model, declaring only these private."""

    return ModelPortfolio(
        entries=tuple(
            ModelPortfolioEntry(
                provider=model.provider,
                model=model.model,
                data_policy=(
                    PRIVATE_DATA_POLICY if model.identifier in private else UNKNOWN_DATA_POLICY
                ),
            )
            for model in create_catalog().models
        )
    )


def substitute(
    workflow: WorkflowSpecification,
    policies: ModelPortfolio,
    sensitivity: Sensitivity | None,
) -> tuple[WorkflowCandidate, ...]:
    return generate_model_substitutions(
        specification=workflow,
        candidate=expensive_candidate(workflow),
        catalog=create_catalog(),
        portfolio=policies,
        registry=create_registry(),
        sensitivity=sensitivity,
    )


def test_a_restricted_context_step_is_substituted_only_by_private_models() -> None:
    substitutions = substitute(
        create_workflow(triage_step()),
        portfolio(CHEAPEST_IDENTIFIER),
        Sensitivity.RESTRICTED,
    )

    assert [bound_models(each) for each in substitutions] == [(CHEAPEST_IDENTIFIER,)]


def test_other_runs_context_steps_are_substituted_by_any_cheaper_model() -> None:
    substitutions = substitute(
        create_workflow(triage_step()),
        portfolio(CHEAPEST_IDENTIFIER),
        Sensitivity.INTERNAL,
    )

    assert [bound_models(each) for each in substitutions] == [
        (CHEAPER_IDENTIFIER,),
        (CHEAPEST_IDENTIFIER,),
    ]


def test_a_fixed_prompt_step_is_substituted_whatever_the_label() -> None:
    substitutions = substitute(
        create_workflow(summary_step()),
        portfolio(),
        Sensitivity.RESTRICTED,
    )

    assert [bound_models(each) for each in substitutions] == [
        (CHEAPER_IDENTIFIER,),
        (CHEAPEST_IDENTIFIER,),
    ]


def test_a_substitute_holds_its_declared_policy() -> None:
    (substitution,) = substitute(
        create_workflow(triage_step()),
        portfolio(CHEAPEST_IDENTIFIER),
        Sensitivity.RESTRICTED,
    )

    (step,) = substitution.steps

    assert isinstance(step.strategy, ContextPromptStrategy)
    assert step.strategy.data_policy == PRIVATE_DATA_POLICY

    unknown = substitute(create_workflow(triage_step()), portfolio(), None)[0].steps[0].strategy

    assert isinstance(unknown, ContextPromptStrategy)
    assert unknown.data_policy == UNKNOWN_DATA_POLICY


# Optimizing


def test_optimizing_restricted_cases_starts_and_stays_on_private_models() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=OPTIMIZED_WORKFLOW_ID,
            name="restricted optimization",
            description="Answer restricted requests.",
        ),
        steps=(
            WorkflowStepSpecification(
                id=OPTIMIZED_STEP_ID,
                specification=ContextPromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=OPTIMIZED_STRATEGY_ID,
                        name="answer",
                        description="Answer the request.",
                    ),
                    template=PromptTemplate(
                        text="Answer: {request}",
                        bindings=(
                            PromptBinding(
                                variable_name="request",
                                event_type="workflow.input.received",
                                field_name="input",
                            ),
                        ),
                    ),
                    model_selection=PortfolioModelSelection(requirements=ModelRequirements()),
                ),
                outputs=(WorkflowValueBinding(name="answer"),),
            ),
        ),
        result=WorkflowValueReference(producer_step_id=OPTIMIZED_STEP_ID, name="answer"),
    )
    runtime = AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(workflow,)),
        models=optimization.create_models(),
        portfolio=ModelPortfolio(
            entries=(
                ModelPortfolioEntry(provider="test-provider", model="cheap"),
                ModelPortfolioEntry(
                    provider="test-provider",
                    model="expensive",
                    data_policy=PRIVATE_DATA_POLICY,
                ),
            )
        ),
        language_models=optimization.create_registry(),
    )
    dataset = BenchmarkDataset(
        name="restricted",
        description="Restricted requests.",
        cases=(
            BenchmarkCase(
                input="claim 412",
                expected=ExpectedOutcome(
                    description="Answered.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
                sensitivity=Sensitivity.RESTRICTED,
            ),
        ),
    )

    session = asyncio.run(
        optimize_configured_workflow(
            runtime=runtime,
            workflow_id=OPTIMIZED_WORKFLOW_ID,
            dataset=dataset,
            scoring_policy=WorkflowScoringPolicy(target_latency_seconds=60.0, target_cost_usd=0.01),
            max_generations=1,
        )
    )

    (initial,) = session.initial_candidates
    (generation,) = session.generations

    assert bound_models(initial) == (optimization.EXPENSIVE_IDENTIFIER,)
    assert [bound_models(each) for each in generation.candidates] == [
        (optimization.EXPENSIVE_IDENTIFIER,)
    ]
