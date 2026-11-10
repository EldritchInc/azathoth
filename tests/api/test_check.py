"""Contract tests for checking a workflow document, and whether it could run here (ADR 0121)."""

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCapability,
    ModelDiscoveryError,
    ModelModality,
    ProviderModel,
)

EXAMPLES = Path(__file__).parents[2] / "examples"

WORKFLOW_ID = UUID("d0000000-0000-4000-8000-000000000001")

COUNT_STEP_ID = UUID("d0000000-0000-4000-8000-000000000011")

ANSWER_STEP_ID = UUID("d0000000-0000-4000-8000-000000000012")

STRATEGY_ID = UUID("d0000000-0000-4000-8000-000000000021")

WORD_COUNT_TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

WORD_COUNT_IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")

MISSING_ID = "d0000000-0000-4000-8000-0000000000ff"

PROVIDER = "provider-a"

ALPHA = ProviderModel(
    provider=PROVIDER,
    model="example/alpha",
    display_name="Alpha",
    input_modalities=frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
    output_modalities=frozenset({ModelModality.TEXT}),
    capabilities=frozenset({ModelCapability.VISION}),
)
"""A model that reads images and text."""

BETA = ProviderModel(
    provider=PROVIDER,
    model="example/beta",
    display_name="Beta",
)
"""A model that reads text alone."""

GAMMA = ProviderModel(
    provider=PROVIDER,
    model="example/gamma",
    display_name="Gamma",
)
"""A model the provider serves, but nothing here can run."""

UNSERVED = f"{PROVIDER}/example/unserved"


def identifier(
    model: ProviderModel,
) -> str:
    """Return a model's provider-qualified identifier."""

    return f"{model.provider}/{model.model}"


class StaticDirectory:
    """A provider directory that serves fixed models."""

    def __init__(
        self,
        models: tuple[ProviderModel, ...],
        *,
        failure: str | None = None,
    ) -> None:
        self._models = models
        self._failure = failure

    @property
    def provider(
        self,
    ) -> str:
        """Return the provider this directory serves."""

        return PROVIDER

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Return the fixed models, or raise the configured failure."""

        if self._failure is not None:
            raise ModelDiscoveryError(self._failure)

        return self._models

    async def model(
        self,
        model: str,
    ) -> ProviderModel | None:
        """Return one fixed model."""

        return next((each for each in self._models if each.model == model), None)


@pytest.fixture
def served(
    location: str,
) -> Iterator[api.Azathoth]:
    """Return an instance serving Alpha, Beta and Gamma, of which Alpha and Beta can run."""

    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory((ALPHA, BETA, GAMMA)),),
        language_models=LanguageModelRegistry(
            {
                identifier(model): DeterministicLanguageModel(
                    provider=model.provider,
                    model=model.model,
                )
                for model in (ALPHA, BETA)
            }
        ),
    ) as instance:
        yield instance


def count_step() -> dict[str, JsonValue]:
    """Return a step counting the words of the run's input with the `word_count` tool."""

    return {
        "id": str(COUNT_STEP_ID),
        "specification": {
            "requirement": {"name": "word_count", "version": "1.0.0", "runtime": "python"},
        },
        "inputs": [
            {
                "name": "text",
                "source": {"event_type": "workflow.input.received", "field_name": "input"},
            }
        ],
        "outputs": [{"name": "count", "path": ["count"]}],
    }


def answer_step(
    model_selection: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """Return a prompt step choosing its model as `model_selection` says, any by default."""

    return {
        "id": str(ANSWER_STEP_ID),
        "specification": {
            "metadata": {
                "id": str(STRATEGY_ID),
                "name": "answer",
                "description": "Answer the request.",
                "version": "1.0.0",
            },
            "prompt": {"text": "Answer the request concisely."},
            "model_selection": (
                model_selection if model_selection is not None else {"requirements": {}}
            ),
        },
        "outputs": [{"name": "answer", "path": []}],
    }


def needing(
    **requirements: JsonValue,
) -> dict[str, JsonValue]:
    """Return a model selection by what a step needs."""

    return {"requirements": dict(requirements)}


def fixed_to(
    model: str,
) -> dict[str, JsonValue]:
    """Return a model selection of one exact model."""

    provider, name = model.split("/", maxsplit=1)

    return {"provider": provider, "model": name}


def document(
    *steps: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Return a workflow of the steps given, whose result is the last step's first output."""

    last = steps[-1]
    outputs = last["outputs"]

    assert isinstance(outputs, list)
    assert isinstance(outputs[0], dict)

    return {
        "metadata": {
            "id": str(WORKFLOW_ID),
            "name": "check me",
            "description": "A workflow to check.",
            "version": "1.0.0",
        },
        "steps": list(steps),
        "result": {"name": outputs[0]["name"]},
    }


def problems(
    check: api.WorkflowCheck,
) -> list[tuple[str, tuple[str | int, ...], UUID | None]]:
    """Return a check's problems as (message, location, step) triples."""

    return [(problem.message, problem.location, problem.step_id) for problem in check.problems]


def word_count(
    instance: api.Azathoth,
) -> None:
    """Import the example `word_count` tool."""

    instance.tools.import_document((EXAMPLES / "tools" / "word-count.json").read_text())


#
# Checking a document
#


def test_a_valid_document_has_no_problems(
    instance: api.Azathoth,
) -> None:
    checked = instance.workflows.check(document(count_step()))

    assert checked == api.WorkflowCheck(valid=True, problems=())
    assert instance.workflows.check(json.dumps(document(count_step()))).valid


def test_every_problem_is_named_with_where_it_is_and_its_step(
    instance: api.Azathoth,
) -> None:
    broken = document(count_step(), answer_step())
    steps = broken["steps"]

    assert isinstance(steps, list)
    assert isinstance(broken["metadata"], dict)

    broken["metadata"]["version"] = 5
    count = steps[0]
    assert isinstance(count, dict)
    count["specification"] = {"requirement": {"name": "", "version": "1.0.0", "runtime": "python"}}

    checked = instance.workflows.check(broken)

    assert not checked.valid
    assert problems(checked) == [
        ("Input should be a valid string", ("metadata", "version"), None),
        (
            "String should have at least 1 character",
            ("steps", 0, "specification", "requirement", "name"),
            COUNT_STEP_ID,
        ),
    ]


def test_a_step_is_checked_as_the_kind_of_step_it_most_nearly_is(
    instance: api.Azathoth,
) -> None:
    broken = document(answer_step())
    steps = broken["steps"]

    assert isinstance(steps, list)
    answer = steps[0]
    assert isinstance(answer, dict)
    specification = answer["specification"]
    assert isinstance(specification, dict)

    del specification["model_selection"]

    assert problems(instance.workflows.check(broken)) == [
        ("Field required", ("steps", 0, "specification", "model_selection"), ANSWER_STEP_ID),
    ]


def test_a_choice_within_a_step_is_checked_as_the_choice_it_most_nearly_is(
    instance: api.Azathoth,
) -> None:
    checked = instance.workflows.check(
        document(answer_step({"provider": PROVIDER, "model": ""})),
    )

    assert problems(checked) == [
        (
            "String should have at least 1 character",
            ("steps", 0, "specification", "model_selection", "model"),
            ANSWER_STEP_ID,
        ),
    ]


def test_a_step_that_is_no_kind_of_step_is_one_problem(
    instance: api.Azathoth,
) -> None:
    step = count_step()
    step["specification"] = "count the words"

    assert problems(instance.workflows.check(document(step))) == [
        ("Input should be an object", ("steps", 0, "specification"), COUNT_STEP_ID),
    ]


def test_a_step_whose_id_is_not_valid_has_no_step(
    instance: api.Azathoth,
) -> None:
    step = count_step()
    step["id"] = "not an id"

    [(message, location, step_id)] = problems(instance.workflows.check(document(step)))

    assert message.startswith("Input should be a valid UUID")
    assert location == ("steps", 0, "id")
    assert step_id is None


def test_a_rule_of_the_whole_workflow_is_a_problem_of_the_whole_document(
    instance: api.Azathoth,
) -> None:
    step = count_step()
    step["depends_on"] = [MISSING_ID]

    assert problems(instance.workflows.check(document(step))) == [
        ("Workflow step dependencies must reference steps in the same workflow.", (), None),
    ]


def test_a_document_without_a_result_cannot_be_imported(
    instance: api.Azathoth,
) -> None:
    resultless = document(count_step())
    del resultless["result"]

    checked = instance.workflows.check(resultless)

    assert not checked.valid
    assert problems(checked) == [(api.RESULT_REQUIRED_MESSAGE, ("result",), None)]


def test_text_that_is_not_json_is_one_problem(
    instance: api.Azathoth,
) -> None:
    [(message, location, step_id)] = problems(instance.workflows.check("{not json"))

    assert message.startswith("Invalid JSON")
    assert location == ()
    assert step_id is None


def test_checking_saves_nothing(
    instance: api.Azathoth,
) -> None:
    instance.workflows.check(document(count_step()))

    assert instance.workflows.list() == ()


def test_a_check_agrees_with_importing(
    instance: api.Azathoth,
) -> None:
    broken = document(count_step())
    del broken["result"]

    for each in (document(count_step()), broken, "{not json"):
        try:
            instance.workflows.import_document(each)
        except api.InvalidDocumentError:
            imported = False
        else:
            imported = True

        assert instance.workflows.check(each).valid is imported


#
# Whether a document could run here
#


def test_a_tool_step_is_ready_with_the_implementation_it_would_run(
    served: api.Azathoth,
) -> None:
    word_count(served)

    readiness = served.runs.readiness(document(count_step()))

    assert readiness == api.WorkflowReadiness(
        ready=True,
        steps=(
            api.StepReadiness(
                step_id=COUNT_STEP_ID,
                kind="tool",
                ready=True,
                models=(),
                tool_id=WORD_COUNT_TOOL_ID,
                tool_version="1.0.0",
                tool_implementation_id=WORD_COUNT_IMPLEMENTATION_ID,
                problem=None,
            ),
        ),
    )


def test_a_tool_step_without_its_tool_says_why(
    served: api.Azathoth,
) -> None:
    readiness = served.runs.readiness(document(count_step()))

    [step] = readiness.steps

    assert not readiness.ready
    assert not step.ready
    assert step.problem == "No tool definition satisfies requirement 'word_count'."
    assert step.tool_id is None
    assert step.tool_implementation_id is None


def test_a_prompt_step_lists_the_models_it_could_run_on_in_the_order_tried(
    served: api.Azathoth,
) -> None:
    for model in (BETA, GAMMA, ALPHA):
        served.portfolio.add(identifier(model))

    [step] = served.runs.readiness(document(answer_step())).steps

    assert step.kind == "prompt"
    assert step.ready
    assert step.models == (identifier(BETA), identifier(ALPHA))
    assert step.problem is None


def test_a_prompt_step_runs_only_on_models_that_meet_its_needs(
    served: api.Azathoth,
) -> None:
    for model in (BETA, ALPHA):
        served.portfolio.add(identifier(model))

    selection = needing(required_input_modalities=["text", "image"])

    [step] = served.runs.readiness(document(answer_step(selection))).steps

    assert step.models == (identifier(ALPHA),)


def test_a_prompt_step_no_model_meets_is_not_ready(
    served: api.Azathoth,
) -> None:
    served.portfolio.add(identifier(BETA))

    selection = needing(required_capabilities=["vision"])

    readiness = served.runs.readiness(document(answer_step(selection)))

    [step] = readiness.steps

    assert not readiness.ready
    assert not step.ready
    assert step.models == ()
    assert step.problem == "No model in the portfolio meets what this step needs."


def test_a_prompt_step_has_no_model_when_the_portfolio_is_empty(
    served: api.Azathoth,
) -> None:
    [step] = served.runs.readiness(document(answer_step())).steps

    assert not step.ready
    assert step.problem == "The portfolio authorizes no model."


def test_a_step_on_one_model_runs_on_it_without_the_portfolio(
    served: api.Azathoth,
) -> None:
    [step] = served.runs.readiness(document(answer_step(fixed_to(identifier(ALPHA))))).steps

    assert step.ready
    assert step.models == (identifier(ALPHA),)


def test_a_step_on_a_model_no_provider_serves_is_not_ready(
    served: api.Azathoth,
) -> None:
    [step] = served.runs.readiness(document(answer_step(fixed_to(UNSERVED)))).steps

    assert not step.ready
    assert step.problem == f"Model {UNSERVED!r} is not currently available."


def test_a_step_on_a_model_served_but_not_runnable_here_says_so(
    served: api.Azathoth,
) -> None:
    [step] = served.runs.readiness(document(answer_step(fixed_to(identifier(GAMMA))))).steps

    assert not step.ready
    assert step.problem == f"Model {identifier(GAMMA)!r} is served, but cannot be run here."


def test_every_step_is_reported_in_the_documents_order(
    served: api.Azathoth,
) -> None:
    word_count(served)

    answer = answer_step(fixed_to(UNSERVED))
    answer["depends_on"] = [str(COUNT_STEP_ID)]

    readiness = served.runs.readiness(document(count_step(), answer))

    assert not readiness.ready
    assert [(step.step_id, step.kind, step.ready) for step in readiness.steps] == [
        (COUNT_STEP_ID, "tool", True),
        (ANSWER_STEP_ID, "prompt", False),
    ]


def test_a_context_prompt_step_is_a_kind_of_its_own(
    served: api.Azathoth,
) -> None:
    served.portfolio.add(identifier(BETA))

    step = answer_step()
    specification = step["specification"]
    assert isinstance(specification, dict)
    del specification["prompt"]
    specification["template"] = {"text": "Answer the request concisely."}

    [readiness] = served.runs.readiness(document(step)).steps

    assert readiness.kind == "context_prompt"
    assert readiness.models == (identifier(BETA),)


def test_readiness_refuses_a_document_that_is_not_valid(
    served: api.Azathoth,
) -> None:
    broken = copy.deepcopy(document(count_step()))
    broken["steps"] = "nope"

    with pytest.raises(api.InvalidDocumentError):
        served.runs.readiness(broken)


def test_readiness_saves_nothing(
    served: api.Azathoth,
) -> None:
    word_count(served)

    served.runs.readiness(document(count_step()))

    assert served.workflows.list() == ()


def test_readiness_says_when_a_provider_cannot_be_asked(
    location: str,
) -> None:
    with (
        api.Azathoth(
            open_repositories(location),
            directories=(StaticDirectory((), failure="Provider is down."),),
        ) as instance,
        pytest.raises(api.ProviderUnavailableError, match="Provider is down."),
    ):
        instance.runs.readiness(document(answer_step()))


def test_a_closed_instance_refuses_checks(
    instance: api.Azathoth,
) -> None:
    instance.close()

    with pytest.raises(api.InstanceClosedError):
        instance.workflows.check(document(count_step()))

    with pytest.raises(api.InstanceClosedError):
        instance.runs.readiness(document(count_step()))
