"""Live step output writers for workflow execution commands."""

from typing import TextIO

from azathoth.cli.rendering import (
    OutputRecord,
    render_output_record,
    step_finished_record,
    step_started_record,
)
from azathoth.workflows import (
    WorkflowRunEvent,
    WorkflowStepStarted,
)


class JsonLinesOutputWriter:
    """Write workflow output records to a stream as JSON Lines.

    As a run observer it writes each step's message record when the step
    starts and its values record when it succeeds, if the step declares
    them. Every line is flushed as it is written, so a reader sees progress
    live.
    """

    def __init__(
        self,
        stream: TextIO,
    ) -> None:
        self._stream = stream

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Write the record one step event produces, if any."""

        record = (
            step_started_record(event)
            if isinstance(
                event,
                WorkflowStepStarted,
            )
            else step_finished_record(event)
        )

        if record is not None:
            self.write(record)

    def write(
        self,
        record: OutputRecord,
    ) -> None:
        """Write and flush one record as a line of JSON."""

        self._stream.write(render_output_record(record) + "\n")
        self._stream.flush()


class TextStepMessageWriter:
    """Write each starting step's message to a stream as a plain line.

    Silent steps write nothing, and step values are never written.
    """

    def __init__(
        self,
        stream: TextIO,
    ) -> None:
        self._stream = stream

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Write the message of a starting step, if it declares one."""

        if not isinstance(
            event,
            WorkflowStepStarted,
        ):
            return

        if event.step.message is None:
            return

        self._stream.write(event.step.message + "\n")
        self._stream.flush()
