"""Contract tests for labelling the input of runs, invocations and trials (ADR 0123).

A process tool reports, as its `count`, the rank of the label in the lineage
its step gives it: 0 public, 1 internal, 2 restricted. What a step's tools see
is what anything the step sends data to would be judged by.
"""

import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.context import INPUT_SENSITIVITY_EVENT_TYPE, context_sensitivity
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from tests.api.test_invoke import promote
from tests.api.test_runs import tool_document, tool_step, workflow

LABEL_TOOL_ID = UUID("d1000000-0000-4000-8000-000000000001")

LABEL_WORKFLOW_ID = UUID("d1000000-0000-4000-8000-000000000003")

LABEL_STEP_ID = UUID("d1000000-0000-4000-8000-000000000011")

BENCHMARK_ID = UUID("d1000000-0000-4000-8000-000000000021")

LABEL_SOURCE = (
    "import json\n"
    "import os\n"
    "import sys\n"
    "\n"
    "json.load(sys.stdin)\n"
    "label = json.loads(os.environ['AZATHOTH_LINEAGE']).get('sensitivity', 'internal')\n"
    "ranks = {'public': 0, 'internal': 1, 'restricted': 2}\n"
    "json.dump({'count': ranks[label]}, sys.stdout)\n"
)


def label_workflow() -> dict[str, JsonValue]:
    return workflow(LABEL_WORKFLOW_ID, tool_step(LABEL_STEP_ID, "label_rank", runtime="process"))


@pytest.fixture
def labelling(
    instance: api.Azathoth,
) -> api.Azathoth:
    """Return an instance with a workflow whose one step reports the label it sees."""

    instance.tools.import_document(
        tool_document(
            LABEL_TOOL_ID,
            "label_rank",
            {
                "runtime": "process",
                "command": [sys.executable],
                "source": LABEL_SOURCE,
                "timeout_seconds": 60.0,
            },
        )
    )
    instance.workflows.import_document(label_workflow())

    return instance


def test_the_api_offers_the_labels() -> None:
    assert api.Sensitivity is Sensitivity


# Runs


@pytest.mark.parametrize(
    ("label", "rank"),
    [(None, 1), (Sensitivity.PUBLIC, 0), (Sensitivity.INTERNAL, 1), (Sensitivity.RESTRICTED, 2)],
)
def test_a_runs_steps_see_the_label_its_input_was_given(
    labelling: api.Azathoth,
    label: Sensitivity | None,
    rank: int,
) -> None:
    result = labelling.runs.run(
        LABEL_WORKFLOW_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=label,
    )

    assert result.result == rank


def test_a_labelled_run_is_kept_with_its_label(
    labelling: api.Azathoth,
    location: str,
) -> None:
    result = labelling.runs.run(
        LABEL_WORKFLOW_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=Sensitivity.RESTRICTED,
    )

    run = open_repositories(location).runs.get(result.run_id)

    assert run is not None
    assert context_sensitivity(run.initial_context) is Sensitivity.RESTRICTED


def test_a_file_given_as_input_takes_the_label_too(
    labelling: api.Azathoth,
) -> None:
    result = labelling.runs.run(
        LABEL_WORKFLOW_ID,
        input=api.RunFile(content=b"claim 412", media_type="text/plain"),
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert result.result == 2


def test_a_label_without_input_starts_no_run(
    labelling: api.Azathoth,
    location: str,
) -> None:
    with pytest.raises(api.InvalidArgumentError) as raised:
        labelling.runs.run(LABEL_WORKFLOW_ID, sensitivity=Sensitivity.RESTRICTED)

    assert str(raised.value) == api.SENSITIVITY_WITHOUT_INPUT_MESSAGE
    assert str(raised.value) == "A sensitivity labels a run's input; give input too."
    assert open_repositories(location).runs.runs() == ()


# Invocations


def test_an_invocations_steps_see_the_label_its_input_was_given(
    labelling: api.Azathoth,
    location: str,
) -> None:
    promote(location, LABEL_WORKFLOW_ID)

    restricted = labelling.runs.invoke(
        LABEL_WORKFLOW_ID,
        input="claim 412",
        sensitivity=Sensitivity.RESTRICTED,
    )
    unlabelled = labelling.runs.invoke(LABEL_WORKFLOW_ID, input="claim 412")

    assert restricted.result == {"result": 2}
    assert unlabelled.result == {"result": 1}

    assert restricted.invocation_id is not None

    invocation = open_repositories(location).invocations.get(restricted.invocation_id)

    assert invocation is not None
    assert [
        event.payload
        for event in invocation.initial_context.events
        if event.event_type == INPUT_SENSITIVITY_EVENT_TYPE
    ] == [{"sensitivity": "restricted"}]


def test_a_label_is_part_of_the_request_its_key_is_recorded_with(
    labelling: api.Azathoth,
    location: str,
) -> None:
    promote(location, LABEL_WORKFLOW_ID)

    first = labelling.runs.invoke(
        LABEL_WORKFLOW_ID,
        input="claim 412",
        sensitivity=Sensitivity.RESTRICTED,
        idempotency_key="claim-412",
    )
    unlabelled = labelling.runs.invoke(
        LABEL_WORKFLOW_ID,
        input="claim 412",
        idempotency_key="claim-412",
    )
    again = labelling.runs.invoke(
        LABEL_WORKFLOW_ID,
        input="claim 412",
        sensitivity=Sensitivity.RESTRICTED,
        idempotency_key="claim-412",
    )

    assert first.status == "succeeded"
    assert unlabelled.status == "rejected"
    assert unlabelled.error is not None
    assert unlabelled.error.code == "idempotency_conflict"
    assert again.replayed


def test_a_file_invocation_takes_the_label_too(
    labelling: api.Azathoth,
    location: str,
) -> None:
    promote(location, LABEL_WORKFLOW_ID)

    outcome = labelling.runs.invoke(
        LABEL_WORKFLOW_ID,
        input=api.RunFile(content=b"claim 412", media_type="text/plain"),
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert outcome.result == {"result": 2}


# Trials


def test_a_tried_step_sees_the_label_of_the_input_given(
    labelling: api.Azathoth,
) -> None:
    tried = labelling.runs.try_step(
        label_workflow(),
        LABEL_STEP_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert tried.step.output == {"count": 2}


def test_a_label_covers_the_inputs_a_tried_step_is_given_without_a_runs_input(
    labelling: api.Azathoth,
) -> None:
    tried = labelling.runs.try_step(
        label_workflow(),
        LABEL_STEP_ID,
        inputs={"text": "claim 412"},
        sensitivity=Sensitivity.RESTRICTED,
    )
    unlabelled = labelling.runs.try_step(
        label_workflow(),
        LABEL_STEP_ID,
        inputs={"text": "claim 412"},
    )

    assert tried.step.output == {"count": 2}
    assert unlabelled.step.output == {"count": 1}


def test_the_documented_label_refusal_is_the_one_raised() -> None:
    readme = Path(__file__).parents[2] / "src" / "azathoth" / "api" / "README.md"

    assert f"\n{api.SENSITIVITY_WITHOUT_INPUT_MESSAGE}\n" in readme.read_text(encoding="utf-8")


# What the views say


def test_a_runs_views_carry_its_label(
    labelling: api.Azathoth,
) -> None:
    restricted = labelling.runs.run(
        LABEL_WORKFLOW_ID,
        input=api.RunInput(payload="claim 412"),
        sensitivity=Sensitivity.RESTRICTED,
    )
    unlabelled = labelling.runs.run(LABEL_WORKFLOW_ID, input=api.RunInput(payload="claim 412"))

    listed = {
        summary.run_id: summary.sensitivity for summary in labelling.runs.list(LABEL_WORKFLOW_ID)
    }

    assert listed == {
        restricted.run_id: Sensitivity.RESTRICTED,
        unlabelled.run_id: Sensitivity.INTERNAL,
    }
    assert labelling.runs.get(restricted.run_id).sensitivity is Sensitivity.RESTRICTED
    assert labelling.runs.get(unlabelled.run_id).sensitivity is Sensitivity.INTERNAL


def test_an_invocations_view_carries_its_label(
    labelling: api.Azathoth,
    location: str,
) -> None:
    promote(location, LABEL_WORKFLOW_ID)

    public = labelling.runs.invoke(
        LABEL_WORKFLOW_ID,
        input="claim 412",
        sensitivity=Sensitivity.PUBLIC,
    )
    unlabelled = labelling.runs.invoke(LABEL_WORKFLOW_ID, input="claim 412")

    assert public.invocation_id is not None
    assert unlabelled.invocation_id is not None
    assert labelling.invocations.get(public.invocation_id).sensitivity is Sensitivity.PUBLIC
    assert labelling.invocations.get(unlabelled.invocation_id).sensitivity is (Sensitivity.INTERNAL)


def test_a_benchmarks_views_carry_its_label(
    instance: api.Azathoth,
) -> None:
    def dataset(
        label: Sensitivity | None,
    ) -> BenchmarkDataset:
        return BenchmarkDataset(
            id=BENCHMARK_ID,
            name="claims",
            description="Claims.",
            cases=(
                BenchmarkCase(
                    id=UUID(int=BENCHMARK_ID.int + 1),
                    input="claim 412",
                    expected=ExpectedOutcome(
                        description="Answered.",
                        value=2,
                        comparison=OutcomeComparison.EXACT,
                    ),
                    sensitivity=label,
                ),
            ),
        )

    instance.benchmarks.import_document(dataset(None).model_dump_json())
    unlabelled = instance.benchmarks.get(BENCHMARK_ID)

    instance.benchmarks.import_document(dataset(Sensitivity.RESTRICTED).model_dump_json())

    (latest, earlier) = instance.benchmarks.history(BENCHMARK_ID)

    assert unlabelled.sensitivity is Sensitivity.INTERNAL
    assert instance.benchmarks.get(BENCHMARK_ID).sensitivity is Sensitivity.RESTRICTED
    assert (latest.sensitivity, earlier.sensitivity) == (
        Sensitivity.RESTRICTED,
        Sensitivity.INTERNAL,
    )
