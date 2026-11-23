"""Running workflows on a remote, reported as they are on this machine (ADR 0140).

`workflow run`, `workflow invoke`, `job run`, `run resume` and
`invocation resume` given `--remote` make their call of the service API
on that remote, where it runs as a job, and report it exactly as the run
on this machine is reported: step messages on standard error in text,
step and value records in JSON Lines, the same terminal record or text,
and the same exit status.

The call runs on a thread of its own while the command waits for it, so
Ctrl-C or SIGTERM cancels the job at the remote before the command
stops, as either stops a run here before it exits. A file given as input
is read and checked here, as `--input-file` is, and sent as a file. A run
a step of another run started takes no `--remote`: it runs where its
parent does.
"""

import base64
import os
import sys
import threading
from collections.abc import Callable
from typing import Final, TypeVar
from uuid import UUID

from pydantic import JsonValue

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.inputs import (
    CLI_INPUT_POLICY,
    WorkflowInputFile,
    resolve_input_file,
)
from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.cli.rendering import (
    ERROR_RECORD_TYPE,
    OUTPUT_RECORD_TYPE,
    RESULT_RECORD_TYPE,
    STEP_RECORD_TYPE,
    OutputRecord,
)
from azathoth.cli.rendering._json import render_json_value
from azathoth.cli.rendering.jobs import render_job_result
from azathoth.cli.rendering.run_details import render_run_detail, run_halted
from azathoth.cli.rendering.sensitivity import warn_if_restricted
from azathoth.cli.reporting import write_terminal_record
from azathoth.cli.service import service_instance
from azathoth.cli.step_output import JsonLinesOutputWriter
from azathoth.inputs import (
    JSON_MEDIA_TYPE,
    InlineInput,
    InMemoryContentStore,
    InputResolutionError,
    InputSourceError,
    ReferenceInput,
    is_binary_media_type,
    resolve_input,
)
from azathoth.jobs import InvokeJobRequest, JobError, JobErrorCode, JobResult, JobStatus
from azathoth.sensitivity import DEFAULT_SENSITIVITY, Sensitivity
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE

CHILD_RUN_MESSAGE: Final = (
    "A run another run's step started runs where its parent runs, so it takes no --remote."
)
"""What a command run by a step of another run says when it is given `--remote`."""

CANCEL_WAIT_SECONDS: Final = 30.0
"""How long a command stopped by Ctrl-C or SIGTERM waits for the remote to stop its job."""

T = TypeVar("T")


def _instance() -> api.Instance:
    """Return the instance connected to the remote `--remote` chose.

    Raises:
        ApiError: The remote cannot be found, or its token is not set.
    """

    return service_instance(CliRuntimeConfiguration.from_environment())


def child_run() -> bool:
    """Return whether this command was started by a step of another run, saying so if it was."""

    if not os.environ.get(LINEAGE_ENVIRONMENT_VARIABLE):
        return False

    print(CHILD_RUN_MESSAGE, file=sys.stderr)

    return True


class LiveOutput:
    """The events of a call on a remote, shown as a run here shows its steps.

    Text writes a starting step's message on standard error; JSON Lines
    writes its message record, and the values record of an executed step
    that emits its values, as the step finishes; result mode stays silent.
    A step's values follow its `step_finished` as `context_changed`, so its
    values record is written once the next event shows whether they came.
    """

    def __init__(
        self,
        output: WorkflowOutputFormat,
        writer: JsonLinesOutputWriter | None,
    ) -> None:
        self._output = output
        self._writer = writer
        self._pending: OutputRecord | None = None

    def __call__(
        self,
        event: object,
    ) -> None:
        """Show one event of the call."""

        if (
            isinstance(event, api.ContextChanged)
            and self._pending is not None
            and self._pending["step_id"] == str(event.step_id)
        ):
            self._pending["values"] = dict(event.values)
            self.flush()

            return

        self.flush()

        if isinstance(event, api.StepStarted) and event.message is not None:
            if self._output is WorkflowOutputFormat.TEXT:
                sys.stderr.write(event.message + "\n")
                sys.stderr.flush()
            elif self._writer is not None:
                self._writer.write(
                    {
                        "type": STEP_RECORD_TYPE,
                        "step_id": str(event.step_id),
                        "message": event.message,
                    }
                )

            return

        if (
            isinstance(event, api.StepFinished)
            and self._writer is not None
            and event.status == "executed"
            and event.emits_values
        ):
            record: OutputRecord = {
                "type": OUTPUT_RECORD_TYPE,
                "step_id": str(event.step_id),
                "values": {},
            }

            if event.confidence is not None:
                record["confidence"] = event.confidence

            self._pending = record

    def flush(
        self,
    ) -> None:
        """Write the values record still waiting for its values, if one is."""

        if self._pending is not None and self._writer is not None:
            self._writer.write(self._pending)

        self._pending = None


def on_remote(
    call: Callable[[api.CancellationToken], T],
) -> T:
    """Make a call of the remote on a thread of its own, and return what it returns.

    Ctrl-C or SIGTERM while it runs cancels its token, which stops its job
    at the remote; the command waits for that, up to `CANCEL_WAIT_SECONDS`,
    and then stops as it was asked to.

    Raises:
        ApiError: The call raised it.
    """

    token = api.CancellationToken()
    outcome: list[T] = []
    raised: list[BaseException] = []

    def make() -> None:
        try:
            outcome.append(call(token))
        except BaseException as error:  # noqa: BLE001 - handed to the waiting thread
            raised.append(error)

    worker = threading.Thread(target=make, name="azathoth-remote-call", daemon=True)
    worker.start()

    try:
        while worker.is_alive():
            worker.join(0.1)
    except BaseException:
        token.cancel()
        worker.join(CANCEL_WAIT_SECONDS)

        raise

    if raised:
        raise raised[0]

    return outcome[0]


def run_record(
    result: api.RunResult,
) -> OutputRecord:
    """Return the terminal record of a run on a remote, as a run here ends its records."""

    error = result.error

    if error is not None and error.code == "workflow_execution_failed":
        return {
            "type": ERROR_RECORD_TYPE,
            "run_id": str(result.run_id),
            "code": error.code,
            "step_id": str(error.step_id),
            "exception_type": error.exception_type,
            "message": error.message,
        }

    if error is not None:
        return {
            "type": ERROR_RECORD_TYPE,
            "run_id": str(result.run_id),
            "code": error.code,
            "message": error.message,
        }

    if not result.has_result:
        return {
            "type": RESULT_RECORD_TYPE,
            "run_id": str(result.run_id),
        }

    return {
        "type": RESULT_RECORD_TYPE,
        "run_id": str(result.run_id),
        "value": result.result,
    }


def input_file(
    given: WorkflowInputFile,
) -> api.RunFile | None:
    """Return a file given as input as a file to send, checked here as `--input-file` is.

    A file that is refused is reported, and None returned.
    """

    store = InMemoryContentStore()

    try:
        resolved = resolve_input_file(given, store=store)
    except (InputSourceError, InputResolutionError) as exc:
        print(str(exc), file=sys.stderr)

        return None

    assert resolved.provenance is not None, "A file read is a reference, so it has provenance."

    return api.RunFile(
        content=_kept(store, resolved.provenance.digest),
        media_type=resolved.provenance.media_type,
    )


def report_run(
    instance: api.Instance,
    result: api.RunResult,
    *,
    output: WorkflowOutputFormat,
    writer: JsonLinesOutputWriter | None,
    sensitivity: Sensitivity | None,
) -> int:
    """Print a run a remote finished as a run here is printed, returning the exit code.

    Text shows the run the remote kept and exits 1 only when it halted; JSON
    Lines and result mode end with its terminal record. A restricted run's
    report is followed by the warning that it holds restricted data. The
    label is the run's own in text, and otherwise `sensitivity`, or the
    kept run's when that is None, as for a resumed run.
    """

    if output is WorkflowOutputFormat.TEXT:
        detail = instance.runs.get(result.run_id)
        print(render_run_detail(detail))
        status = 1 if run_halted(detail) else 0
        label = detail.sensitivity
    else:
        status = write_terminal_record(run_record(result), writer)
        label = instance.runs.get(result.run_id).sensitivity if sensitivity is None else sensitivity

    warn_if_restricted(label, f"Run {result.run_id}")

    return status


def run_on_remote(
    workflow_id: UUID,
    *,
    payload: JsonValue | None,
    given: bool,
    workflow_file: WorkflowInputFile | None,
    output: WorkflowOutputFormat,
    sensitivity: Sensitivity | None,
) -> int:
    """Run a workflow on a remote and report it as `workflow run` reports one here."""

    run_input: api.RunInput | api.RunFile | None = None

    if workflow_file is not None:
        run_input = input_file(workflow_file)

        if run_input is None:
            return 1
    elif given:
        run_input = api.RunInput(payload=payload)

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None
    live = LiveOutput(output, writer)

    try:
        instance = _instance()
        result = on_remote(
            lambda token: instance.runs.run(
                workflow_id,
                input=run_input,
                sensitivity=sensitivity,
                on_event=live,
                cancel=token,
            )
        )
        live.flush()

        return report_run(
            instance,
            result,
            output=output,
            writer=writer,
            sensitivity=sensitivity if sensitivity is not None else DEFAULT_SENSITIVITY,
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1


def resume_run_on_remote(
    run_id: UUID,
    *,
    output: WorkflowOutputFormat,
) -> int:
    """Resume a run on a remote and report it as `run resume` reports one here."""

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None
    live = LiveOutput(output, writer)

    try:
        instance = _instance()
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    try:
        result = on_remote(lambda token: instance.runs.resume(run_id, on_event=live, cancel=token))
        live.flush()

        return report_run(instance, result, output=output, writer=writer, sensitivity=None)
    except api.NotFoundError:
        print(f"Run {run_id} has no journal to resume.", file=sys.stderr)

        return 1
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1


def invocation_record(
    outcome: api.InvocationOutcome,
) -> OutputRecord:
    """Return the terminal record of an invocation on a remote, as one here ends its records.

    A request that made no outcome, one rejected or still running, ends
    with the error record a keyed invocation here ends with.
    """

    if outcome.status == "succeeded":
        return {
            "type": RESULT_RECORD_TYPE,
            "invocation_id": str(outcome.invocation_id),
            "value": outcome.result,
        }

    assert outcome.error is not None, "An invocation that did not succeed says why."

    record: OutputRecord = {
        "type": ERROR_RECORD_TYPE,
        "code": outcome.error.code,
        "message": outcome.error.message,
    }

    if outcome.invocation_id is not None:
        record = {"type": ERROR_RECORD_TYPE, "invocation_id": str(outcome.invocation_id), **record}

    if outcome.status == "failed" and outcome.error.metadata:
        record["metadata"] = dict(outcome.error.metadata)

    return record


def report_invocation(
    outcome: api.InvocationOutcome,
    *,
    output: WorkflowOutputFormat,
    writer: JsonLinesOutputWriter | None,
    sensitivity: Sensitivity,
) -> int:
    """Print an invocation a remote finished as one here is printed, returning the exit code.

    Text prints a success on standard output and a failure on standard
    error, and a request that made no outcome only its message there.
    """

    finished = outcome.status in ("succeeded", "failed")

    if output is WorkflowOutputFormat.TEXT:
        if outcome.status == "succeeded":
            print(
                "\n".join(
                    (
                        f"Invocation ID: {outcome.invocation_id}",
                        "Status: succeeded",
                        "Result:",
                        render_json_value(outcome.result),
                    )
                )
            )
            status = 0
        else:
            assert outcome.error is not None, "An invocation that did not succeed says why."

            if finished:
                lines = [
                    f"Invocation ID: {outcome.invocation_id}",
                    "Status: failed",
                    f"Error: {outcome.error.code}",
                    f"Message: {outcome.error.message}",
                ]

                if outcome.error.metadata:
                    lines.extend(("Metadata:", render_json_value(outcome.error.metadata)))

                print("\n".join(lines), file=sys.stderr)
            else:
                print(outcome.error.message, file=sys.stderr)

            status = 1
    else:
        status = write_terminal_record(invocation_record(outcome), writer)

    if finished:
        warn_if_restricted(sensitivity, f"Invocation {outcome.invocation_id}")

    return status


def invoke_on_remote(
    workflow_id: UUID,
    *,
    payload: JsonValue | WorkflowInputFile,
    output: WorkflowOutputFormat,
    idempotency_key: str | None,
    sensitivity: Sensitivity | None,
) -> int:
    """Invoke a workflow on a remote and report it as `workflow invoke` reports one here."""

    invocation_input: JsonValue | api.RunFile

    if isinstance(payload, WorkflowInputFile):
        sent = input_file(payload)

        if sent is None:
            return 1

        invocation_input = sent
    else:
        invocation_input = payload

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None
    live = LiveOutput(output, writer)

    try:
        instance = _instance()
        outcome = on_remote(
            lambda token: instance.runs.invoke(
                workflow_id,
                input=invocation_input,
                sensitivity=sensitivity,
                idempotency_key=idempotency_key,
                on_event=live,
                cancel=token,
            )
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    live.flush()

    return report_invocation(
        outcome,
        output=output,
        writer=writer,
        sensitivity=sensitivity if sensitivity is not None else DEFAULT_SENSITIVITY,
    )


def resume_invocation_on_remote(
    invocation_id: UUID,
    *,
    output: WorkflowOutputFormat,
) -> int:
    """Resume an invocation on a remote and report it as `invocation resume` reports one here."""

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None
    live = LiveOutput(output, writer)

    try:
        instance = _instance()
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    try:
        outcome = on_remote(
            lambda token: instance.invocations.resume(invocation_id, on_event=live, cancel=token)
        )
        live.flush()
        sensitivity = instance.invocations.get(invocation_id).sensitivity
    except api.NotFoundError:
        print(f"Invocation {invocation_id} was not found.", file=sys.stderr)

        return 1
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    return report_invocation(outcome, output=output, writer=writer, sensitivity=sensitivity)


def _kept(
    store: InMemoryContentStore,
    digest: str,
) -> bytes:
    """Return the content a file read here was kept under, in the store it was read into."""

    content = store.get(digest)

    assert content is not None, "A file read is kept in the store it was read into."

    return content


def _request_input(
    source: InlineInput | ReferenceInput,
) -> JsonValue | api.RunFile:
    """Return a job request's input as the service API takes it.

    A file it names is read and checked here, under the command line's
    policy; JSON is sent as its value, and other inline content as a file.

    Raises:
        InputResolutionError: The file cannot be read, is too large, or does
            not decode as its media type.
    """

    if isinstance(source, InlineInput) and source.media_type == JSON_MEDIA_TYPE:
        return source.value

    if isinstance(source, InlineInput):
        content = (
            base64.b64decode(str(source.value))
            if is_binary_media_type(source.media_type)
            else str(source.value).encode("utf-8")
        )

        return api.RunFile(content=content, media_type=source.media_type)

    store = InMemoryContentStore()
    resolved = resolve_input(source, policy=CLI_INPUT_POLICY, store=store)

    assert resolved.provenance is not None, "A reference read has provenance."

    return api.RunFile(
        content=_kept(store, resolved.provenance.digest),
        media_type=resolved.provenance.media_type,
    )


def job_result(
    outcome: api.InvocationOutcome,
) -> JobResult:
    """Return the result envelope an invocation's outcome on a remote stands for."""

    return JobResult(
        idempotency_key=outcome.idempotency_key,
        status=JobStatus(outcome.status),
        replayed=outcome.replayed,
        invocation_id=outcome.invocation_id,
        result=outcome.result,
        error=(
            JobError(
                code=JobErrorCode(outcome.error.code),
                message=outcome.error.message,
                metadata=dict(outcome.error.metadata),
            )
            if outcome.error is not None
            else None
        ),
    )


def run_job_on_remote(
    request: InvokeJobRequest,
) -> int:
    """Run one decoded job request on a remote, and print its result envelope as here.

    A file the request names is read here; one that cannot be read is the
    `invalid_input` envelope it is here.
    """

    try:
        invocation_input = _request_input(request.input)
    except InputResolutionError as exc:
        print(
            render_job_result(
                JobResult(
                    idempotency_key=request.idempotency_key,
                    status=JobStatus.REJECTED,
                    invocation_id=None,
                    error=JobError(code=JobErrorCode.INVALID_INPUT, message=str(exc)),
                )
            )
        )

        return 1

    try:
        instance = _instance()
        outcome = on_remote(
            lambda token: instance.runs.invoke(
                request.workflow_id,
                input=invocation_input,
                sensitivity=request.input.sensitivity,
                idempotency_key=request.idempotency_key,
                caller_metadata=request.caller_metadata,
                cancel=token,
            )
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(render_job_result(job_result(outcome)))

    if outcome.invocation_id is not None:
        warn_if_restricted(
            request.input.sensitivity or DEFAULT_SENSITIVITY,
            f"Invocation {outcome.invocation_id}",
        )

    return 0 if outcome.status == "succeeded" else 1


__all__ = [
    "CANCEL_WAIT_SECONDS",
    "CHILD_RUN_MESSAGE",
    "LiveOutput",
    "child_run",
    "input_file",
    "invocation_record",
    "invoke_on_remote",
    "job_result",
    "on_remote",
    "report_invocation",
    "report_run",
    "resume_invocation_on_remote",
    "resume_run_on_remote",
    "run_job_on_remote",
    "run_on_remote",
    "run_record",
]
