"""Tests that a restricted run's prompt reaches only a model that may receive it (ADR 0123)."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import (
    Context,
    LineageRun,
    LineageStep,
    StepLineage,
    running_step,
)
from azathoth.prompting import (
    ContextPromptStrategy,
    ModelBinding,
    PromptBinding,
    PromptTemplate,
    RestrictedInputRefusedError,
    generate_context_prompt_candidates,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelResponse,
    Prompt,
)
from azathoth.sensitivity import (
    PRIVATE_DATA_POLICY,
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    PolicyAnswer,
    Sensitivity,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import create_workflow_input_event
from tests.prompting.test_context_candidates import (
    FIRST_IDENTIFIER,
    SECOND_IDENTIFIER,
    create_catalog,
    create_registry,
    create_specification,
)

STEP_ID = UUID("a1230000-0000-4000-8000-000000000003")

RETAINING = DataPolicy(retains_data=PolicyAnswer.YES, trains_on_data=PolicyAnswer.NO)


class RecordingModel:
    """A language model that records each prompt it is sent."""

    def __init__(self) -> None:
        self.prompts: list[Prompt] = []
        self._model = DeterministicLanguageModel(
            provider="provider-a",
            model="classifier",
            response_text="positive",
        )

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt and reply with fixed text."""

        self.prompts.append(prompt)

        return await self._model.complete(prompt)


def strategy(
    model: RecordingModel,
    data_policy: DataPolicy | None,
) -> ContextPromptStrategy:
    return ContextPromptStrategy(
        metadata=StrategyMetadata(
            id=UUID(int=1),
            name="Classify",
            description="Classify the claim.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text="Classify: {claim}",
            bindings=(
                PromptBinding(
                    variable_name="claim",
                    event_type="workflow.input.received",
                    field_name="input",
                ),
            ),
        ),
        language_model=model,
        model_binding=ModelBinding(identifier=FIRST_IDENTIFIER),
        data_policy=data_policy,
    )


def step(
    sensitivity: Sensitivity | None,
) -> StepLineage:
    return StepLineage(
        step=LineageStep(
            workflow_id=UUID(int=10),
            run_id=UUID(int=11),
            step_id=STEP_ID,
            attempt=1,
        ),
        depth=0,
        root=LineageRun(workflow_id=UUID(int=10), run_id=UUID(int=11)),
        sensitivity=sensitivity,
    )


CONTEXT = Context(events=(create_workflow_input_event("claim 412", producer="test"),))


def run_in(
    lineage: StepLineage | None,
    target: ContextPromptStrategy,
) -> object:
    async def run() -> object:
        if lineage is None:
            return (await target.run(CONTEXT)).output

        with running_step(lineage):
            return (await target.run(CONTEXT)).output

    return asyncio.run(run())


# Sending


@pytest.mark.parametrize(
    ("policy", "reason"),
    [
        (None, "it is not in the portfolio."),
        (
            UNKNOWN_DATA_POLICY,
            "its portfolio entry does not say whether its provider retains data, and does not "
            "say whether it trains on data.",
        ),
        (RETAINING, "its portfolio entry says its provider retains data."),
    ],
    ids=["outside-portfolio", "undeclared", "retaining"],
)
def test_a_restricted_steps_prompt_is_not_sent_to_a_model_that_may_not_receive_it(
    policy: DataPolicy | None,
    reason: str,
) -> None:
    model = RecordingModel()

    with pytest.raises(RestrictedInputRefusedError) as caught:
        run_in(step(Sensitivity.RESTRICTED), strategy(model, policy))

    assert str(caught.value) == (
        f"Step {STEP_ID} sent nothing. {FIRST_IDENTIFIER} cannot receive restricted input: "
        f"{reason} If its provider neither retains nor trains on data, declare that with "
        f"`azathoth model policy {FIRST_IDENTIFIER} --no-retention --no-training`; "
        "otherwise choose a model that may receive restricted input."
    )
    assert model.prompts == []


def test_a_restricted_steps_prompt_is_sent_to_a_private_model() -> None:
    model = RecordingModel()

    assert run_in(step(Sensitivity.RESTRICTED), strategy(model, PRIVATE_DATA_POLICY)) == "positive"
    assert len(model.prompts) == 1


@pytest.mark.parametrize("label", [None, Sensitivity.PUBLIC, Sensitivity.INTERNAL])
@pytest.mark.parametrize("policy", [None, UNKNOWN_DATA_POLICY, RETAINING])
def test_other_steps_prompts_are_sent_to_any_model(
    label: Sensitivity | None,
    policy: DataPolicy | None,
) -> None:
    model = RecordingModel()

    assert run_in(step(label), strategy(model, policy)) == "positive"
    assert len(model.prompts) == 1


def test_a_prompt_rendered_outside_a_step_is_not_judged() -> None:
    model = RecordingModel()

    assert run_in(None, strategy(model, None)) == "positive"


def test_a_refusal_without_a_model_binding_names_the_strategy() -> None:
    target = ContextPromptStrategy(
        metadata=StrategyMetadata(
            id=UUID(int=1),
            name="Classify",
            description="Classify the claim.",
            version="1.0.0",
        ),
        template=PromptTemplate(text="Classify."),
        language_model=RecordingModel(),
    )

    with pytest.raises(RestrictedInputRefusedError) as caught:
        run_in(step(Sensitivity.RESTRICTED), target)

    assert str(caught.value).startswith(
        f"Step {STEP_ID} sent nothing. Classify cannot receive restricted input"
    )


# Candidates


def portfolio(
    first: DataPolicy = UNKNOWN_DATA_POLICY,
    second: DataPolicy = UNKNOWN_DATA_POLICY,
) -> ModelPortfolio:
    return ModelPortfolio(
        entries=(
            ModelPortfolioEntry(provider="provider-a", model="classifier", data_policy=first),
            ModelPortfolioEntry(provider="provider-b", model="classifier", data_policy=second),
        )
    )


def identifiers(
    candidates: tuple[ContextPromptStrategy, ...],
) -> list[str]:
    return [
        candidate.model_binding.identifier
        for candidate in candidates
        if candidate.model_binding is not None
    ]


def test_each_candidate_holds_its_models_declared_policy() -> None:
    candidates = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=portfolio(second=PRIVATE_DATA_POLICY),
    )

    assert [candidate.data_policy for candidate in candidates] == [
        UNKNOWN_DATA_POLICY,
        PRIVATE_DATA_POLICY,
    ]


def test_a_fixed_model_holds_its_portfolio_policy_or_none_outside_it() -> None:
    (inside,) = generate_context_prompt_candidates(
        specification=create_specification(fixed=True),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=portfolio(first=PRIVATE_DATA_POLICY),
    )
    (outside,) = generate_context_prompt_candidates(
        specification=create_specification(fixed=True),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=ModelPortfolio(),
    )

    assert inside.data_policy == PRIVATE_DATA_POLICY
    assert outside.data_policy is None


def test_a_restricted_run_tries_models_that_may_receive_it_first() -> None:
    candidates = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=portfolio(second=PRIVATE_DATA_POLICY),
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert identifiers(candidates) == [SECOND_IDENTIFIER, FIRST_IDENTIFIER]


@pytest.mark.parametrize(
    ("label", "first", "second"),
    [
        (None, UNKNOWN_DATA_POLICY, PRIVATE_DATA_POLICY),
        (Sensitivity.INTERNAL, UNKNOWN_DATA_POLICY, PRIVATE_DATA_POLICY),
        (Sensitivity.PUBLIC, UNKNOWN_DATA_POLICY, PRIVATE_DATA_POLICY),
        (Sensitivity.RESTRICTED, PRIVATE_DATA_POLICY, PRIVATE_DATA_POLICY),
        (Sensitivity.RESTRICTED, UNKNOWN_DATA_POLICY, RETAINING),
    ],
    ids=["unlabelled", "internal", "public", "both-private", "neither-private"],
)
def test_otherwise_the_models_keep_their_order(
    label: Sensitivity | None,
    first: DataPolicy,
    second: DataPolicy,
) -> None:
    candidates = generate_context_prompt_candidates(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=portfolio(first, second),
        sensitivity=label,
    )

    assert identifiers(candidates) == [FIRST_IDENTIFIER, SECOND_IDENTIFIER]
