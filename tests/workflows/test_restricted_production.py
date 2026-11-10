"""Tests that a restricted invocation sends its input only to models that may receive it (ADR 0123).

Production chooses its models from the production state. The portfolio, as
it is when the invocation runs, supplies only each model's declared policy.
"""

import asyncio
from pathlib import Path

import pytest

from azathoth.prompting import (
    ContextPromptStrategy,
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import ModelPortfolio, ModelPortfolioEntry, Prompt
from azathoth.sensitivity import (
    PRIVATE_DATA_POLICY,
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    Sensitivity,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryRunJournalRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowRunRepository,
    WorkflowProductionState,
    WorkflowRunner,
    complete_production_invocation,
    create_production_invocation,
    generate_production_workflow_candidate,
    resolve_production_model_selection,
    resume_production_invocation,
)
from tests.workflows.test_context_prompt_production import (
    PRIMARY,
    STEP_ID,
    STRATEGY_ID,
    SUBSTITUTE,
    WORKFLOW_ID,
    create_state,
    current,
)


def portfolio(
    primary: DataPolicy = UNKNOWN_DATA_POLICY,
    substitute: DataPolicy = UNKNOWN_DATA_POLICY,
) -> ModelPortfolio:
    return ModelPortfolio(
        entries=(
            ModelPortfolioEntry(provider="test", model="primary", data_policy=primary),
            ModelPortfolioEntry(provider="test", model="substitute", data_policy=substitute),
        )
    )


def resolved(
    *,
    sensitivity: Sensitivity | None,
    policies: ModelPortfolio | None,
    state: WorkflowProductionState | None = None,
    executable: tuple[FixedModelSelection, ...] = (PRIMARY, SUBSTITUTE),
) -> FixedModelSelection:
    catalog, registry = current(*executable)

    return resolve_production_model_selection(
        state=state if state is not None else create_state(),
        step_id=STEP_ID,
        catalog=catalog,
        registry=registry,
        portfolio=policies,
        sensitivity=sensitivity,
    )


# Resolution


def test_a_restricted_invocation_runs_on_a_private_substitute() -> None:
    assert (
        resolved(
            sensitivity=Sensitivity.RESTRICTED,
            policies=portfolio(substitute=PRIVATE_DATA_POLICY),
        )
        == SUBSTITUTE
    )


def test_a_restricted_invocation_keeps_a_private_primary() -> None:
    assert (
        resolved(
            sensitivity=Sensitivity.RESTRICTED,
            policies=portfolio(PRIVATE_DATA_POLICY, PRIVATE_DATA_POLICY),
        )
        == PRIMARY
    )


def test_a_private_model_must_also_be_executable() -> None:
    assert (
        resolved(
            sensitivity=Sensitivity.RESTRICTED,
            policies=portfolio(substitute=PRIVATE_DATA_POLICY),
            executable=(PRIMARY,),
        )
        == PRIMARY
    )


@pytest.mark.parametrize(
    ("label", "policies"),
    [
        (None, portfolio(substitute=PRIVATE_DATA_POLICY)),
        (Sensitivity.INTERNAL, portfolio(substitute=PRIVATE_DATA_POLICY)),
        (Sensitivity.RESTRICTED, portfolio()),
        (Sensitivity.RESTRICTED, None),
    ],
    ids=["unlabelled", "internal", "restricted-none-private", "restricted-no-portfolio"],
)
def test_otherwise_the_primary_runs_as_before(
    label: Sensitivity | None,
    policies: ModelPortfolio | None,
) -> None:
    assert resolved(sensitivity=label, policies=policies) == PRIMARY


def test_a_fixed_prompts_model_does_not_depend_on_the_label() -> None:
    state = create_state()
    (step,) = state.specification.steps

    fixed = step.model_copy(
        update={
            "specification": PromptStrategySpec(
                metadata=StrategyMetadata(
                    id=STRATEGY_ID,
                    name="greet",
                    description="Greet.",
                    version="1.0.0",
                ),
                prompt=Prompt(text="Say hello."),
                model_selection=PRIMARY,
            )
        }
    )
    fixed_state = state.model_copy(
        update={"specification": state.specification.model_copy(update={"steps": (fixed,)})}
    )

    assert (
        resolved(
            sensitivity=Sensitivity.RESTRICTED,
            policies=portfolio(substitute=PRIVATE_DATA_POLICY),
            state=fixed_state,
        )
        == PRIMARY
    )


# Candidates


def test_a_production_candidate_holds_the_portfolios_policies() -> None:
    catalog, registry = current(PRIMARY, SUBSTITUTE)

    candidate = generate_production_workflow_candidate(
        state=create_state(),
        catalog=catalog,
        registry=registry,
        portfolio=portfolio(substitute=PRIVATE_DATA_POLICY),
        sensitivity=Sensitivity.RESTRICTED,
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(strategy, ContextPromptStrategy)
    assert strategy.model_binding is not None
    assert strategy.model_binding.identifier == SUBSTITUTE.identifier
    assert strategy.data_policy == PRIVATE_DATA_POLICY


def test_a_production_candidate_without_a_portfolio_holds_no_policy() -> None:
    catalog, registry = current(PRIMARY, SUBSTITUTE)

    candidate = generate_production_workflow_candidate(
        state=create_state(),
        catalog=catalog,
        registry=registry,
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(strategy, ContextPromptStrategy)
    assert strategy.data_policy is None


# Invocations


def invoke(
    tmp_path: Path,
    *,
    sensitivity: Sensitivity | None,
    policies: ModelPortfolio | None,
) -> ProductionInvocationSuccess | ProductionInvocationFailure:
    database = tmp_path / "azathoth.db"
    catalog, registry = current(PRIMARY, SUBSTITUTE)
    invocation_repository = SQLiteProductionInvocationRepository(database)
    run_repository = SQLiteWorkflowRunRepository(database)

    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="Claim 412.",
        sensitivity=sensitivity,
    )

    invocation_repository.save(invocation)

    result = asyncio.run(
        complete_production_invocation(
            invocation=invocation,
            state=create_state(),
            catalog=catalog,
            registry=registry,
            runner=WorkflowRunner(),
            run_repository=run_repository,
            invocation_repository=invocation_repository,
            invocation_run_repository=SQLiteProductionInvocationRunRepository(database),
            portfolio=policies,
        )
    )

    assert isinstance(result, ProductionInvocationSuccess | ProductionInvocationFailure)

    return result


def test_a_restricted_invocation_is_answered_by_its_private_substitute(
    tmp_path: Path,
) -> None:
    result = invoke(
        tmp_path,
        sensitivity=Sensitivity.RESTRICTED,
        policies=portfolio(substitute=PRIVATE_DATA_POLICY),
    )

    assert isinstance(result, ProductionInvocationSuccess)
    assert result.result == {"result": "answered by substitute"}


def test_a_restricted_invocation_with_no_private_model_fails_and_says_why(
    tmp_path: Path,
) -> None:
    result = invoke(tmp_path, sensitivity=Sensitivity.RESTRICTED, policies=portfolio())

    assert isinstance(result, ProductionInvocationFailure)

    (run,) = SQLiteWorkflowRunRepository(tmp_path / "azathoth.db").runs()
    (step,) = run.steps
    failure = step.attempts[-1].failure

    assert failure is not None
    assert failure.exception_type == "RestrictedInputRefusedError"
    assert failure.message.startswith(
        f"Step {STEP_ID} sent nothing. {PRIMARY.identifier} cannot receive restricted input"
    )


def test_an_unlabelled_invocation_is_answered_by_its_primary(
    tmp_path: Path,
) -> None:
    result = invoke(tmp_path, sensitivity=None, policies=portfolio(substitute=PRIVATE_DATA_POLICY))

    assert isinstance(result, ProductionInvocationSuccess)
    assert result.result == {"result": "answered by primary"}


# Resuming


@pytest.mark.parametrize(
    ("policies", "answered"),
    [(portfolio(substitute=PRIVATE_DATA_POLICY), True), (None, False)],
    ids=["private-substitute", "no-portfolio"],
)
def test_a_resumed_restricted_invocation_reads_the_portfolio_it_is_given(
    policies: ModelPortfolio | None,
    answered: bool,
) -> None:
    catalog, registry = current(PRIMARY, SUBSTITUTE)
    invocations = InMemoryProductionInvocationRepository()
    journal = InMemoryRunJournalRepository()
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="Claim 412.",
        sensitivity=Sensitivity.RESTRICTED,
    )

    invocations.save(invocation)

    result = asyncio.run(
        resume_production_invocation(
            invocation=invocation,
            revisions=(),
            current_state=create_state(),
            catalog=catalog,
            registry=registry,
            runner=WorkflowRunner(journal=journal),
            journal=journal,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_repository=invocations,
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
            portfolio=policies,
        )
    )

    assert isinstance(result, ProductionInvocationSuccess) is answered
