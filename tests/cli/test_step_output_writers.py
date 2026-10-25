"""Tests for live step output writers."""

import asyncio
import dataclasses
import io
import json

from azathoth.cli.step_output import (
    JsonLinesOutputWriter,
    TextStepMessageWriter,
)
from azathoth.context import Context
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowFailurePolicy,
    WorkflowRunner,
    WorkflowRunObserver,
)
from tests.workflows.test_run_observation import (
    FIRST_STEP_ID,
    FIRST_STRATEGY_ID,
    SECOND_STEP_ID,
    SECOND_STRATEGY_ID,
    THIRD_STEP_ID,
    THIRD_STRATEGY_ID,
    CountingExecutor,
    create_candidate,
    create_step,
)


def create_announced_chain() -> WorkflowCandidate:
    """Create an emitting counter, an announced reporter, and a silent archiver."""

    return create_candidate(
        dataclasses.replace(
            create_step(
                step_id=FIRST_STEP_ID,
                strategy_id=FIRST_STRATEGY_ID,
                name="Counter",
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            message="Counting words",
            emit_values=True,
        ),
        dataclasses.replace(
            create_step(
                step_id=SECOND_STEP_ID,
                strategy_id=SECOND_STRATEGY_ID,
                name="Reporter",
                depends_on=(FIRST_STEP_ID,),
            ),
            message="Writing the report",
        ),
        create_step(
            step_id=THIRD_STEP_ID,
            strategy_id=THIRD_STRATEGY_ID,
            name="Archiver",
            depends_on=(SECOND_STEP_ID,),
        ),
    )


def run_observed(
    observer: WorkflowRunObserver,
    *,
    executor: CountingExecutor,
) -> None:
    """Run the announced chain under one observer."""

    asyncio.run(
        WorkflowRunner(
            executor=executor,
            observer=observer,
        ).run_recording_failures(
            create_announced_chain(),
            Context(),
        )
    )


def test_json_lines_writer_streams_messages_and_emitted_values() -> None:
    stream = io.StringIO()

    run_observed(
        JsonLinesOutputWriter(stream),
        executor=CountingExecutor(),
    )

    assert [json.loads(line) for line in stream.getvalue().splitlines()] == [
        {
            "type": "step",
            "step_id": str(FIRST_STEP_ID),
            "message": "Counting words",
        },
        {
            "type": "output",
            "step_id": str(FIRST_STEP_ID),
            "values": {
                "count": 7,
            },
        },
        {
            "type": "step",
            "step_id": str(SECOND_STEP_ID),
            "message": "Writing the report",
        },
    ]


def test_json_lines_writer_writes_nothing_for_a_failed_step_after_its_message() -> None:
    stream = io.StringIO()

    run_observed(
        JsonLinesOutputWriter(stream),
        executor=CountingExecutor(
            failing=frozenset({"Counter"}),
        ),
    )

    records = [json.loads(line) for line in stream.getvalue().splitlines()]

    assert [(record["type"], record["step_id"]) for record in records] == [
        ("step", str(FIRST_STEP_ID)),
        ("step", str(SECOND_STEP_ID)),
    ]


def test_json_lines_writer_writes_one_record_per_line() -> None:
    stream = io.StringIO()

    JsonLinesOutputWriter(stream).write(
        {
            "type": "result",
            "value": 4,
        }
    )

    assert stream.getvalue() == '{"type": "result", "value": 4}\n'


def test_text_writer_writes_only_step_messages() -> None:
    stream = io.StringIO()

    run_observed(
        TextStepMessageWriter(stream),
        executor=CountingExecutor(),
    )

    assert stream.getvalue() == "Counting words\nWriting the report\n"
