"""Tests for building benchmark cases from recorded workflow runs."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import OutcomeComparison
from azathoth.workflows import (
    SOURCE_FEEDBACK_METADATA_KEY,
    SOURCE_RUN_METADATA_KEY,
    WORKFLOW_INPUT_EVENT_TYPE,
    BenchmarkCaseSourceError,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
    WorkflowStepRun,
    WorkflowStepStatus,
    benchmark_case_from_run,
    create_workflow_input_event,
    latest_corrected_output,
    workflow_run_input,
)

RUN_ID = UUID("44444444-4444-4444-4444-444444444444")
OTHER_RUN_ID = UUID("55555555-5555-5555-5555-555555555555")
WORKFLOW_ID = UUID("66666666-6666-6666-6666-666666666666")
STEP_ID = UUID("77777777-7777-7777-7777-777777777777")
FIRST_FEEDBACK_ID = UUID("88888888-8888-8888-8888-888888888881")
SECOND_FEEDBACK_ID = UUID("88888888-8888-8888-8888-888888888882")
THIRD_FEEDBACK_ID = UUID("88888888-8888-8888-8888-888888888883")

STARTED_AT = datetime(2026, 10, 25, 18, 0, tzinfo=UTC)

INPUT: JsonValue = {
    "text": "the old ones wait",
}


def input_event(
    payload: JsonValue = INPUT,
) -> ContextEvent:
    """Create one canonical workflow input event."""

    return create_workflow_input_event(
        payload,
        producer="azathoth.test",
        occurred_at=STARTED_AT,
    )


def create_run(
    *events: ContextEvent,
) -> WorkflowRun:
    """Create one recorded run starting with the given context events."""

    return WorkflowRun(
        id=RUN_ID,
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Word count",
            description="Count words.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.SKIPPED,
            ),
        ),
        initial_context=Context(
            events=events,
        ),
        final_context=Context(
            events=events,
        ),
        started_at=STARTED_AT,
        completed_at=STARTED_AT,
    )


def bad_feedback(
    feedback_id: UUID,
    *,
    corrected: JsonValue,
    minutes: int,
    run_id: UUID = RUN_ID,
) -> WorkflowRunFeedback:
    """Create bad feedback recorded some minutes after the run started."""

    return WorkflowRunFeedback(
        id=feedback_id,
        run_id=run_id,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="Miscounted.",
        corrected_output=corrected,
        created_at=STARTED_AT + timedelta(minutes=minutes),
    )


def good_feedback(
    feedback_id: UUID,
    *,
    minutes: int,
) -> WorkflowRunFeedback:
    """Create good feedback recorded some minutes after the run started."""

    return WorkflowRunFeedback(
        id=feedback_id,
        run_id=RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
        created_at=STARTED_AT + timedelta(minutes=minutes),
    )


def test_workflow_run_input_returns_the_received_payload() -> None:
    assert workflow_run_input(create_run(input_event())) == INPUT


def test_workflow_run_input_returns_received_null() -> None:
    assert workflow_run_input(create_run(input_event(None))) is None


def test_workflow_run_input_ignores_other_events() -> None:
    run = create_run(
        ContextEvent(
            event_type="production.invocation.received",
            payload={"input": "ignored"},
            producer="azathoth.test",
        ),
        input_event(),
    )

    assert workflow_run_input(run) == INPUT


def test_workflow_run_input_rejects_a_run_without_input() -> None:
    with pytest.raises(BenchmarkCaseSourceError) as raised:
        workflow_run_input(create_run())

    assert str(raised.value) == f"Run {RUN_ID} did not receive workflow input."


def test_workflow_run_input_rejects_an_input_event_without_an_input_key() -> None:
    run = create_run(
        ContextEvent(
            event_type=WORKFLOW_INPUT_EVENT_TYPE,
            payload={"other": 1},
            producer="azathoth.test",
        ),
    )

    with pytest.raises(BenchmarkCaseSourceError) as raised:
        workflow_run_input(run)

    assert str(raised.value) == f"Run {RUN_ID} did not receive workflow input."


def test_workflow_run_input_rejects_input_received_more_than_once() -> None:
    with pytest.raises(BenchmarkCaseSourceError) as raised:
        workflow_run_input(
            create_run(
                input_event(),
                input_event({"text": "again"}),
            )
        )

    assert str(raised.value) == f"Run {RUN_ID} received workflow input more than once."


def test_latest_corrected_output_is_none_without_feedback() -> None:
    assert latest_corrected_output(()) is None


def test_latest_corrected_output_picks_the_newest_correction() -> None:
    newest = bad_feedback(
        SECOND_FEEDBACK_ID,
        corrected=4,
        minutes=10,
    )

    assert (
        latest_corrected_output(
            (
                newest,
                bad_feedback(
                    FIRST_FEEDBACK_ID,
                    corrected=3,
                    minutes=5,
                ),
            )
        )
        == newest
    )


def test_latest_corrected_output_breaks_timestamp_ties_by_insertion_order() -> None:
    later = bad_feedback(
        SECOND_FEEDBACK_ID,
        corrected=4,
        minutes=5,
    )

    assert (
        latest_corrected_output(
            (
                bad_feedback(
                    FIRST_FEEDBACK_ID,
                    corrected=3,
                    minutes=5,
                ),
                later,
            )
        )
        == later
    )


def test_latest_corrected_output_ignores_later_good_feedback() -> None:
    correction = bad_feedback(
        FIRST_FEEDBACK_ID,
        corrected=4,
        minutes=5,
    )

    assert (
        latest_corrected_output(
            (
                correction,
                good_feedback(
                    SECOND_FEEDBACK_ID,
                    minutes=10,
                ),
            )
        )
        == correction
    )


def test_latest_corrected_output_ignores_later_bad_feedback_without_a_correction() -> None:
    correction = bad_feedback(
        FIRST_FEEDBACK_ID,
        corrected=4,
        minutes=5,
    )

    assert (
        latest_corrected_output(
            (
                correction,
                bad_feedback(
                    SECOND_FEEDBACK_ID,
                    corrected=None,
                    minutes=10,
                ),
            )
        )
        == correction
    )


def test_latest_corrected_output_is_none_when_no_feedback_corrects() -> None:
    assert (
        latest_corrected_output(
            (
                good_feedback(
                    FIRST_FEEDBACK_ID,
                    minutes=5,
                ),
                bad_feedback(
                    SECOND_FEEDBACK_ID,
                    corrected=None,
                    minutes=10,
                ),
            )
        )
        is None
    )


def test_latest_corrected_output_never_takes_a_value_from_good_feedback() -> None:
    good_with_value = WorkflowRunFeedback(
        id=THIRD_FEEDBACK_ID,
        run_id=RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
        corrected_output=9,
        created_at=STARTED_AT + timedelta(minutes=20),
    )

    assert latest_corrected_output((good_with_value,)) is None


def test_benchmark_case_from_run_replays_the_input_and_expects_the_value() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=4,
    )

    assert case.input == INPUT
    assert case.expected.value == 4
    assert case.expected.comparison is OutcomeComparison.EXACT


def test_benchmark_case_from_run_names_the_source_run_by_default() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=4,
    )

    assert case.expected.description == f"Added from run {RUN_ID}."


def test_benchmark_case_from_run_uses_a_supplied_description() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=4,
        description="  Four words.  ",
    )

    assert case.expected.description == "Four words."


def test_benchmark_case_from_run_treats_a_blank_description_as_absent() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=4,
        description="   ",
    )

    assert case.expected.description == f"Added from run {RUN_ID}."


def test_benchmark_case_from_run_records_the_source_run() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=4,
    )

    assert case.metadata == {
        SOURCE_RUN_METADATA_KEY: str(RUN_ID),
    }


def test_benchmark_case_from_run_records_the_source_feedback() -> None:
    feedback = bad_feedback(
        FIRST_FEEDBACK_ID,
        corrected=4,
        minutes=5,
    )

    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=4,
        feedback=feedback,
    )

    assert case.metadata == {
        SOURCE_RUN_METADATA_KEY: str(RUN_ID),
        SOURCE_FEEDBACK_METADATA_KEY: str(FIRST_FEEDBACK_ID),
    }


def test_benchmark_case_source_metadata_keys() -> None:
    assert SOURCE_RUN_METADATA_KEY == "source_run_id"
    assert SOURCE_FEEDBACK_METADATA_KEY == "source_feedback_id"


def test_benchmark_case_from_run_gives_each_case_a_new_identity() -> None:
    run = create_run(input_event())

    first = benchmark_case_from_run(
        run,
        comparison=OutcomeComparison.EXACT,
        expected=4,
    )
    second = benchmark_case_from_run(
        run,
        comparison=OutcomeComparison.EXACT,
        expected=4,
    )

    assert first.id != second.id


def test_benchmark_case_from_run_accepts_an_expected_null() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=None,
    )

    assert case.expected.value is None


def test_benchmark_case_from_run_rejects_a_run_without_input() -> None:
    with pytest.raises(BenchmarkCaseSourceError) as raised:
        benchmark_case_from_run(
            create_run(),
            comparison=OutcomeComparison.EXACT,
            expected=4,
        )

    assert str(raised.value) == f"Run {RUN_ID} did not receive workflow input."


def test_benchmark_case_from_run_rejects_feedback_for_another_run() -> None:
    with pytest.raises(BenchmarkCaseSourceError) as raised:
        benchmark_case_from_run(
            create_run(input_event()),
            comparison=OutcomeComparison.EXACT,
            expected=4,
            feedback=bad_feedback(
                FIRST_FEEDBACK_ID,
                corrected=4,
                minutes=5,
                run_id=OTHER_RUN_ID,
            ),
        )

    assert str(raised.value) == f"Feedback {FIRST_FEEDBACK_ID} does not judge run {RUN_ID}."


def test_benchmark_case_from_run_accepts_a_valid_schema_expectation() -> None:
    schema: JsonValue = {
        "type": "integer",
        "minimum": 0,
    }

    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.SCHEMA,
        expected=schema,
    )

    assert case.expected.value == schema


def test_benchmark_case_from_run_rejects_a_non_schema_value_for_schema_comparison() -> None:
    with pytest.raises(BenchmarkCaseSourceError) as raised:
        benchmark_case_from_run(
            create_run(input_event()),
            comparison=OutcomeComparison.SCHEMA,
            expected=4,
        )

    assert str(raised.value) == (
        "Expected value cannot be used with comparison 'schema': "
        "A JSON Schema must be an object or a boolean."
    )


def test_benchmark_case_from_run_rejects_an_invalid_schema_for_schema_comparison() -> None:
    with pytest.raises(BenchmarkCaseSourceError) as raised:
        benchmark_case_from_run(
            create_run(input_event()),
            comparison=OutcomeComparison.SCHEMA,
            expected={"type": 4},
        )

    assert str(raised.value).startswith(
        "Expected value cannot be used with comparison 'schema': Invalid JSON Schema: "
    )


def test_benchmark_case_from_run_accepts_any_value_for_semantic_comparison() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.SEMANTIC,
        expected="four words",
    )

    assert case.expected.comparison is OutcomeComparison.SEMANTIC
