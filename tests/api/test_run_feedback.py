"""Contract tests for a person's judgment of a kept run, through the service API (ADR 0129)."""

import time

import pytest

from azathoth import api
from tests.api.test_models import parses
from tests.api.test_run_history import count
from tests.api.test_runs import COUNT_WORKFLOW_ID, MISSING_ID, stock


def judged(
    instance: api.Azathoth,
) -> api.RunResult:
    """Stock the instance, and return one kept run of the word count workflow."""

    stock(instance)

    return count(instance, "one two")


def test_a_good_judgment_is_recorded_and_returned(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)

    feedback = instance.runs.record_feedback(run.run_id, "good")

    assert feedback.run_id == run.run_id
    assert feedback.disposition == "good"
    assert feedback.reason is None
    assert feedback.corrected_output is None
    assert feedback.created_at.tzinfo is not None
    assert feedback.command == f"azathoth run show {run.run_id}"
    assert parses(feedback.command)


def test_a_bad_judgment_keeps_its_reason_and_what_it_should_have_produced(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)

    feedback = instance.runs.record_feedback(
        run.run_id,
        "bad",
        reason="  It counted a hyphen as a word.  ",
        corrected_output={"count": 1},
    )

    assert feedback.disposition == "bad"
    assert feedback.reason == "It counted a hyphen as a word."
    assert feedback.corrected_output == {"count": 1}


def test_a_blank_reason_is_no_reason(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)

    assert instance.runs.record_feedback(run.run_id, "good", reason="   ").reason is None


def test_a_bad_judgment_needs_a_reason(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)

    for reason in (None, "  "):
        with pytest.raises(api.InvalidArgumentError) as refused:
            instance.runs.record_feedback(run.run_id, "bad", reason=reason)

        assert str(refused.value) == "Bad workflow run feedback requires a reason."

    assert instance.runs.feedback(run.run_id) == ()


def test_a_corrected_output_only_accompanies_a_bad_judgment(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)

    with pytest.raises(api.InvalidArgumentError) as refused:
        instance.runs.record_feedback(run.run_id, "good", corrected_output=2)

    assert str(refused.value) == "A corrected output can only accompany bad feedback."
    assert instance.runs.feedback(run.run_id) == ()


def test_a_judgment_is_good_or_bad(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)

    with pytest.raises(api.InvalidArgumentError) as refused:
        instance.runs.record_feedback(run.run_id, "meh")

    assert str(refused.value) == "disposition must be good or bad, not 'meh'."


def test_a_run_that_was_never_kept_is_not_judged(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as recording:
        instance.runs.record_feedback(MISSING_ID, "good")

    with pytest.raises(api.NotFoundError) as reading:
        instance.runs.feedback(MISSING_ID)

    assert str(recording.value) == f"Run {MISSING_ID} was not found."
    assert str(reading.value) == f"Run {MISSING_ID} was not found."


def test_a_runs_judgments_are_listed_newest_first(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)

    first = instance.runs.record_feedback(run.run_id, "bad", reason="Wrong.")
    time.sleep(0.002)
    second = instance.runs.record_feedback(run.run_id, "good")

    assert [feedback.feedback_id for feedback in instance.runs.feedback(run.run_id)] == [
        second.feedback_id,
        first.feedback_id,
    ]


def test_a_run_shows_its_latest_judgment_and_none_before_it_is_judged(
    instance: api.Azathoth,
) -> None:
    run = judged(instance)
    unjudged = count(instance, "three")

    instance.runs.record_feedback(run.run_id, "good")
    time.sleep(0.002)
    instance.runs.record_feedback(run.run_id, "bad", reason="Wrong after all.")

    listed = {summary.run_id: summary.feedback for summary in instance.runs.list(COUNT_WORKFLOW_ID)}

    assert listed == {run.run_id: "bad", unjudged.run_id: None}
    assert instance.runs.get(run.run_id).feedback == "bad"
    assert instance.runs.get(unjudged.run_id).feedback is None
