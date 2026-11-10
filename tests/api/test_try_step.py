"""Contract tests for trying one step of a workflow document (ADR 0121)."""

from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.inputs import content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from tests.api.test_runs import (
    COUNT_STEP_ID,
    FAIL_IMPLEMENTATION_ID,
    FAIL_STEP_ID,
    MEASURE_STEP_ID,
    MISSING_ID,
    PDF,
    SLEEP_STEP_ID,
    stock,
    stock_measure,
    tool_step,
    workflow,
)

TRIAL_WORKFLOW_ID = UUID("f0000000-0000-4000-8000-000000000001")

RECOUNT_STEP_ID = UUID("f0000000-0000-4000-8000-000000000011")

FAILURE_MESSAGE = f"Tool implementation {FAIL_IMPLEMENTATION_ID} failed during execution."


def recount_step() -> dict[str, JsonValue]:
    """Return a step counting the words of what the count step counted, if it counted 99."""

    step = tool_step(RECOUNT_STEP_ID, "word_count")
    step["depends_on"] = [str(COUNT_STEP_ID)]
    step["inputs"] = [
        {"name": "text", "source": {"producer_step_id": str(COUNT_STEP_ID), "name": "count"}}
    ]
    step["outputs"] = [{"name": "recount", "path": ["count"]}]
    step["conditions"] = [
        {"source": {"producer_step_id": str(COUNT_STEP_ID), "name": "count"}, "expected": 99}
    ]

    return step


def trial(
    *steps: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Return a workflow document of the steps given, never imported."""

    document = workflow(TRIAL_WORKFLOW_ID, steps[-1])
    document["steps"] = list(steps)
    outputs = steps[-1]["outputs"]

    assert isinstance(outputs, list)
    assert isinstance(outputs[0], dict)

    document["result"] = {"name": outputs[0]["name"]}

    return document


def counting(
    count_source: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """Return a two-step document: a count of the run's input, then a recount of it."""

    count = tool_step(COUNT_STEP_ID, "word_count")

    if count_source is not None:
        count["inputs"] = [{"name": "text", "source": count_source}]

    return trial(count, recount_step())


#
# Trying a step
#


def test_a_step_is_tried_on_the_inputs_given_and_nothing_is_kept(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)

    tried = instance.runs.try_step(
        counting(),
        RECOUNT_STEP_ID,
        inputs={"text": "that is not dead"},
    )

    step = tried.step

    assert step.step_id == RECOUNT_STEP_ID
    assert step.status == "executed"
    assert step.layer == 0
    assert step.attempts == 1
    assert step.output == {"count": 4}
    assert step.values == {"recount": 4}
    assert step.failures == ()
    assert tried.warnings == ()
    assert open_repositories(location).runs.runs() == ()

    with pytest.raises(api.NotFoundError):
        instance.workflows.get(TRIAL_WORKFLOW_ID)


def test_a_steps_conditions_are_not_asked(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    tried = instance.runs.try_step(counting(), RECOUNT_STEP_ID, inputs={"text": "one"})

    assert tried.step.status == "executed"


def test_an_input_read_from_the_runs_input_reads_the_input_given(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    tried = instance.runs.try_step(
        counting(),
        COUNT_STEP_ID,
        input=api.RunInput(payload="one two three"),
    )

    assert tried.step.values == {"count": 3}


def test_an_input_read_from_a_runs_input_it_was_not_given_fails_as_in_a_run(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    tried = instance.runs.try_step(counting(), COUNT_STEP_ID)

    assert tried.step.status == "failed"
    assert tried.step.failures[0].exception_type == "WorkflowInputResolutionError"


def test_an_input_given_takes_the_place_of_its_source(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    tried = instance.runs.try_step(
        counting(),
        COUNT_STEP_ID,
        input=api.RunInput(payload="one two three"),
        inputs={"text": "one"},
    )

    assert tried.step.values == {"count": 1}


def test_a_constant_input_keeps_its_value_unless_another_is_given(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    document = counting({"value": "one two"})

    kept = instance.runs.try_step(document, COUNT_STEP_ID)
    given = instance.runs.try_step(document, COUNT_STEP_ID, inputs={"text": "one two three"})

    assert kept.step.values == {"count": 2}
    assert given.step.values == {"count": 3}


def test_a_file_is_an_input_kept_by_its_digest(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock_measure(instance)

    measure = tool_step(MEASURE_STEP_ID, "measure")
    measure["inputs"] = [
        {
            "name": "document",
            "source": {"event_type": "workflow.input.received", "field_name": "input"},
        }
    ]

    tried = instance.runs.try_step(
        trial(measure),
        MEASURE_STEP_ID,
        inputs={"document": api.RunFile(content=PDF, media_type="application/pdf")},
    )

    assert tried.step.values == {"count": len(PDF)}
    assert open_repositories(location).content.get(content_bytes_digest(PDF)) == PDF


def test_a_step_that_cannot_start_keeps_no_file_it_was_given(
    instance: api.Azathoth,
    location: str,
) -> None:
    measure = tool_step(MEASURE_STEP_ID, "measure")

    with pytest.raises(api.RunNotStartedError):
        instance.runs.try_step(
            trial(measure),
            MEASURE_STEP_ID,
            inputs={"text": api.RunFile(content=PDF, media_type="application/pdf")},
        )

    assert not open_repositories(location).content.contains(content_bytes_digest(PDF))


def test_a_file_that_is_not_its_media_type_is_refused(
    instance: api.Azathoth,
) -> None:
    stock_measure(instance)

    with pytest.raises(api.InvalidArgumentError):
        instance.runs.try_step(
            counting(),
            COUNT_STEP_ID,
            inputs={"text": api.RunFile(content=b"not a pdf", media_type="application/pdf")},
        )


def test_a_failing_step_is_retried_as_its_policy_says(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    explode = tool_step(FAIL_STEP_ID, "explode")
    explode["retry_policy"] = {"max_attempts": 2, "initial_delay_seconds": 0.0}

    tried = instance.runs.try_step(trial(explode), FAIL_STEP_ID, inputs={"text": "x"})

    assert tried.step.status == "failed"
    assert tried.step.attempts == 2
    assert tried.step.failures == (
        api.StepFailure(attempt=1, exception_type="ToolExecutionError", message=FAILURE_MESSAGE),
        api.StepFailure(attempt=2, exception_type="ToolExecutionError", message=FAILURE_MESSAGE),
    )


def test_a_tried_step_reports_its_events_as_it_runs(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    events: list[api.RunEvent] = []

    instance.runs.try_step(
        counting(),
        RECOUNT_STEP_ID,
        inputs={"text": "one two"},
        on_event=events.append,
    )

    assert events == [
        api.StepStarted(step_id=RECOUNT_STEP_ID, layer=0, message=None),
        api.StepFinished(
            step_id=RECOUNT_STEP_ID,
            layer=0,
            status="executed",
            failure=None,
            confidence=None,
        ),
        api.ContextChanged(step_id=RECOUNT_STEP_ID, values={"recount": 2}),
    ]


def test_a_callback_that_raises_is_named_in_a_warning(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    def explode(event: api.RunEvent) -> None:
        raise RuntimeError("boom")

    tried = instance.runs.try_step(
        counting(),
        RECOUNT_STEP_ID,
        inputs={"text": "one"},
        on_event=explode,
    )

    assert tried.step.status == "executed"
    assert len(tried.warnings) == 1
    assert "boom" in tried.warnings[0]


#
# Refusals
#


def test_an_input_the_step_does_not_take_is_refused(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    with pytest.raises(api.InvalidArgumentError) as raised:
        instance.runs.try_step(counting(), RECOUNT_STEP_ID, inputs={"text": "a", "words": "b"})

    assert str(raised.value) == f"Step {RECOUNT_STEP_ID} has no input 'words'."


def test_an_input_from_another_step_must_be_given(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    with pytest.raises(api.InvalidArgumentError) as raised:
        instance.runs.try_step(counting(), RECOUNT_STEP_ID)

    assert str(raised.value) == (
        f"Step {RECOUNT_STEP_ID} input 'text' takes a value another step produces, "
        "so trying the step alone needs it given."
    )


def test_a_step_the_document_does_not_have_is_not_found(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    with pytest.raises(api.NotFoundError) as raised:
        instance.runs.try_step(counting(), MISSING_ID)

    assert str(raised.value) == f"The workflow document has no step {MISSING_ID}."


def test_a_document_that_is_not_valid_is_refused(
    instance: api.Azathoth,
) -> None:
    broken = counting()
    broken["steps"] = "nope"

    with pytest.raises(api.InvalidDocumentError):
        instance.runs.try_step(broken, COUNT_STEP_ID)


def test_a_step_whose_tool_is_missing_never_starts(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.RunNotStartedError):
        instance.runs.try_step(counting(), COUNT_STEP_ID, inputs={"text": "a"})


#
# Cancelling
#


def test_a_cancelled_try_stops_and_raises(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    token = api.CancellationToken()

    def cancel_when_started(event: api.RunEvent) -> None:
        if event.type == "step_started":
            token.cancel()

    sleep = tool_step(SLEEP_STEP_ID, "slow_count", runtime="process")

    with pytest.raises(api.RunCancelledError):
        instance.runs.try_step(
            trial(sleep),
            SLEEP_STEP_ID,
            inputs={"text": "x"},
            on_event=cancel_when_started,
            cancel=token,
        )


def test_a_token_cancelled_beforehand_tries_nothing(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock_measure(instance)
    token = api.CancellationToken()
    token.cancel()
    events: list[api.RunEvent] = []
    measure = tool_step(MEASURE_STEP_ID, "measure")

    with pytest.raises(api.RunCancelledError):
        instance.runs.try_step(
            trial(measure),
            MEASURE_STEP_ID,
            inputs={"text": api.RunFile(content=PDF, media_type="application/pdf")},
            on_event=events.append,
            cancel=token,
        )

    assert events == []
    assert not open_repositories(location).content.contains(content_bytes_digest(PDF))


def test_a_closed_instance_tries_nothing(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.runs.try_step(counting(), COUNT_STEP_ID)
