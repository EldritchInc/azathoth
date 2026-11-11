"""Contract tests that restricted runs prompt only models that may receive them (ADR 0123).

Beta's portfolio entry declares nothing, so it may not receive restricted
input; Alpha's is declared private, so it may.
"""

import copy
from collections.abc import Iterator

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import DeterministicLanguageModel, LanguageModelRegistry
from tests.api.test_check import (
    ALPHA,
    ANSWER_STEP_ID,
    BETA,
    WORKFLOW_ID,
    StaticDirectory,
    answer_step,
    document,
    fixed_to,
    identifier,
)
from tests.api.test_invoke import promote

PRIVATE = api.DataPolicy(retains_data=api.PolicyAnswer.NO, trains_on_data=api.PolicyAnswer.NO)


@pytest.fixture
def served(
    location: str,
) -> Iterator[api.Azathoth]:
    """Return an instance serving Alpha and Beta, each answering with its own name."""

    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory((ALPHA, BETA)),),
        language_models=LanguageModelRegistry(
            {
                identifier(model): DeterministicLanguageModel(
                    provider=model.provider,
                    model=model.model,
                    response_text=model.display_name,
                )
                for model in (ALPHA, BETA)
            }
        ),
    ) as instance:
        yield instance


@pytest.fixture
def authorized(
    served: api.Azathoth,
) -> api.Azathoth:
    """Return the instance with Beta, then Alpha, in its portfolio; only Alpha private."""

    served.portfolio.add(identifier(BETA))
    served.portfolio.add(identifier(ALPHA), data_policy=PRIVATE)

    return served


def context_step(
    model_selection: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """Return a context prompt step showing a model the run's input."""

    step = answer_step(model_selection)
    specification = step["specification"]

    assert isinstance(specification, dict)

    del specification["prompt"]
    specification["template"] = {
        "text": "Answer: {request}",
        "bindings": [
            {
                "variable_name": "request",
                "event_type": "workflow.input.received",
                "field_name": "input",
            }
        ],
    }

    return step


def restricted_failure(
    detail: api.RunStepDetail,
) -> str:
    (failure,) = detail.failures

    assert failure.exception_type == "RestrictedInputRefusedError"

    return failure.message


# Readiness


def test_a_restricted_context_step_could_run_only_on_private_models(
    authorized: api.Azathoth,
) -> None:
    [unlabelled] = authorized.runs.readiness(document(context_step())).steps
    [restricted] = authorized.runs.readiness(
        document(context_step()),
        sensitivity=api.Sensitivity.RESTRICTED,
    ).steps

    assert unlabelled.models == (identifier(BETA), identifier(ALPHA))
    assert restricted.ready
    assert restricted.models == (identifier(ALPHA),)


def test_a_restricted_context_step_with_no_private_model_is_not_ready(
    served: api.Azathoth,
) -> None:
    served.portfolio.add(identifier(BETA))

    readiness = served.runs.readiness(
        document(context_step()),
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    [step] = readiness.steps

    assert not readiness.ready
    assert not step.ready
    assert step.models == ()
    assert step.problem == (
        f"{identifier(BETA)} cannot receive restricted input: its portfolio entry does not say "
        "whether its provider retains data, and does not say whether it trains on data. "
        "If its provider neither retains nor trains on data, declare that with "
        f"`azathoth model policy {identifier(BETA)} --no-retention --no-training`; "
        "otherwise choose a model that may receive restricted input."
    )


def test_a_fixed_prompt_shows_no_run_data_and_is_ready_on_any_model(
    authorized: api.Azathoth,
) -> None:
    [step] = authorized.runs.readiness(
        document(answer_step()),
        sensitivity=api.Sensitivity.RESTRICTED,
    ).steps

    assert step.ready
    assert step.models == (identifier(BETA), identifier(ALPHA))


# Matching


def test_only_private_models_match_for_restricted_input(
    authorized: api.Azathoth,
) -> None:
    def matching(
        sensitivity: api.Sensitivity | None,
    ) -> list[str]:
        return [
            model.identifier for model in authorized.models.matching({}, sensitivity=sensitivity)
        ]

    assert matching(None) == [identifier(BETA), identifier(ALPHA)]
    assert matching(api.Sensitivity.PUBLIC) == [identifier(BETA), identifier(ALPHA)]
    assert matching(api.Sensitivity.RESTRICTED) == [identifier(ALPHA)]


# Runs


def test_a_restricted_run_is_answered_by_a_private_model(
    authorized: api.Azathoth,
) -> None:
    authorized.workflows.import_document(document(context_step()))

    unlabelled = authorized.runs.run(WORKFLOW_ID, input=api.RunInput(payload="claim 412"))
    restricted = authorized.runs.run(
        WORKFLOW_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    assert unlabelled.result == BETA.display_name
    assert restricted.result == ALPHA.display_name


def test_a_restricted_run_with_no_private_model_sends_nothing(
    served: api.Azathoth,
) -> None:
    served.portfolio.add(identifier(BETA))
    served.workflows.import_document(document(context_step()))

    result = served.runs.run(
        WORKFLOW_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    assert not result.succeeded

    detail = served.runs.get(result.run_id)
    (step,) = detail.steps

    assert restricted_failure(step).startswith(
        f"Step {ANSWER_STEP_ID} sent nothing. {identifier(BETA)} cannot receive restricted input"
    )


def test_a_tried_restricted_step_is_refused_on_a_model_outside_the_portfolio(
    served: api.Azathoth,
) -> None:
    trial = served.runs.try_step(
        document(context_step(fixed_to(identifier(BETA)))),
        ANSWER_STEP_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    assert trial.step.status == "failed"
    assert restricted_failure(trial.step).endswith(
        f"{identifier(BETA)} cannot receive restricted input: it is not in the portfolio. "
        "If its provider neither retains nor trains on data, declare that with "
        f"`azathoth model policy {identifier(BETA)} --no-retention --no-training`; "
        "otherwise choose a model that may receive restricted input."
    )


def test_a_tried_restricted_step_runs_on_a_private_model(
    authorized: api.Azathoth,
) -> None:
    trial = authorized.runs.try_step(
        document(context_step()),
        ANSWER_STEP_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    assert trial.step.output == ALPHA.display_name


# Invocations


def test_an_invocation_reads_the_portfolio_as_it_is_when_it_runs(
    served: api.Azathoth,
    location: str,
) -> None:
    served.portfolio.add(identifier(ALPHA))
    served.workflows.import_document(
        copy.deepcopy(document(context_step(fixed_to(identifier(ALPHA)))))
    )
    promote(location, WORKFLOW_ID)

    refused = served.runs.invoke(
        WORKFLOW_ID,
        input="claim 412",
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    served.portfolio.set_data_policy(identifier(ALPHA), PRIVATE)

    answered = served.runs.invoke(
        WORKFLOW_ID,
        input="claim 412",
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    assert refused.status == "failed"
    assert answered.status == "succeeded"
    assert answered.result == {"result": ALPHA.display_name}


def test_an_unlabelled_invocation_runs_on_any_model(
    served: api.Azathoth,
    location: str,
) -> None:
    served.workflows.import_document(document(context_step(fixed_to(identifier(BETA)))))
    promote(location, WORKFLOW_ID)

    outcome = served.runs.invoke(WORKFLOW_ID, input="claim 412")

    assert outcome.status == "succeeded"
    assert outcome.result == {"result": BETA.display_name}
