"""Running job requests: replay, conflict, resolution, invocation (ADR 0097)."""

from collections.abc import Callable, Mapping
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from azathoth.inputs import (
    ContentStore,
    InputPolicy,
    InputProvenance,
    InputResolutionError,
    resolve_input,
)
from azathoth.jobs.decoding import (
    JobRequestError,
    decode_job_request,
    parse_job_request,
)
from azathoth.jobs.digest import job_request_digest
from azathoth.jobs.envelope import (
    InvokeJobRequest,
    JobError,
    JobErrorCode,
    JobResult,
    incomplete_job_result,
    job_result_from_invocation,
    rejected_job_result,
)
from azathoth.runtime import AzathothRuntime
from azathoth.workflows import (
    IdempotencyKeyInUseError,
    InvocationIdempotency,
    ProductionInvocationRepository,
    ProductionInvocationResult,
    ProductionInvocationRunRepository,
    WorkflowRunner,
    WorkflowRunRepository,
    invoke_production_workflow,
)


class JobInvoker(Protocol):
    """Invoke one workflow against its active production state for a job.

    An entry point binds this to its runtime, so the runtime is composed only
    when a job actually invokes a workflow: a replay, a conflict or a
    rejection needs none.

    The invoker records the invocation, with its idempotency, before anything
    runs, and raises `IdempotencyKeyInUseError`, saving nothing, when another
    invocation already holds the key.
    """

    async def __call__(
        self,
        *,
        workflow_id: UUID,
        payload: JsonValue,
        caller_metadata: Mapping[str, JsonValue],
        input_provenance: InputProvenance | None,
        idempotency: InvocationIdempotency,
    ) -> ProductionInvocationResult:
        """Invoke one workflow and return its terminal result."""

        ...


def runtime_job_invoker(
    load_runtime: Callable[[], AzathothRuntime],
    *,
    invocation_repository: ProductionInvocationRepository,
    run_repository: WorkflowRunRepository,
    invocation_run_repository: ProductionInvocationRunRepository,
    runner: WorkflowRunner | None = None,
) -> JobInvoker:
    """Return an invoker that composes its runtime only when it invokes.

    `load_runtime` is called once, on the first invocation, so a job that is
    replayed, conflicts or is rejected never loads provider state or
    credentials.
    """

    runtimes: list[AzathothRuntime] = []

    async def invoke(
        *,
        workflow_id: UUID,
        payload: JsonValue,
        caller_metadata: Mapping[str, JsonValue],
        input_provenance: InputProvenance | None,
        idempotency: InvocationIdempotency,
    ) -> ProductionInvocationResult:
        if not runtimes:
            runtimes.append(load_runtime())

        runtime = runtimes[0]

        return await invoke_production_workflow(
            workflow_id=workflow_id,
            payload=payload,
            caller_metadata=caller_metadata,
            production_state=runtime.production_state(
                workflow_id,
            ),
            catalog=runtime.models,
            registry=runtime.language_models,
            invocation_repository=invocation_repository,
            run_repository=run_repository,
            invocation_run_repository=invocation_run_repository,
            runner=runner,
            tool_resolver=runtime.tool_resolver,
            tool_implementation_resolver=runtime.tool_implementation_resolver,
            input_provenance=input_provenance,
            idempotency=idempotency,
        )

    return invoke


async def run_invoke_job(
    request: InvokeJobRequest,
    *,
    policy: InputPolicy,
    store: ContentStore,
    invocation_repository: ProductionInvocationRepository,
    invoke: JobInvoker,
) -> JobResult:
    """Run one decoded invoke job request.

    In order:

    1. The request is digested, and its key looked up. A key recorded with the
       same digest replays its invocation, as `succeeded` or `failed`, or
       `incomplete` when it has no result; a key recorded with a different
       digest is an `idempotency_conflict`. Nothing is resolved or run.
    2. The input is resolved under the entry point's policy. A failure is
       rejected as `invalid_input`, and records nothing.
    3. The workflow is invoked with the key and digest. Should another
       request have recorded the key in the meantime, that request's
       invocation is reported instead, and nothing runs.
    """

    key = request.idempotency_key
    digest = job_request_digest(request)

    recorded = recorded_job_result(
        key,
        request_digest=digest,
        invocation_repository=invocation_repository,
    )

    if recorded is not None:
        return recorded

    try:
        resolved = resolve_input(
            request.input,
            policy=policy,
            store=store,
        )
    except InputResolutionError as exc:
        return rejected_job_result(
            JobError(
                code=JobErrorCode.INVALID_INPUT,
                message=str(exc),
            ),
            idempotency_key=key,
        )

    try:
        result = await invoke(
            workflow_id=request.workflow_id,
            payload=resolved.value,
            caller_metadata=request.caller_metadata,
            input_provenance=resolved.provenance,
            idempotency=InvocationIdempotency(
                key=key,
                request_digest=digest,
            ),
        )
    except IdempotencyKeyInUseError:
        raced = recorded_job_result(
            key,
            request_digest=digest,
            invocation_repository=invocation_repository,
        )

        if raced is None:
            raise

        return raced

    return job_result_from_invocation(
        result,
        idempotency_key=key,
    )


async def run_job(
    data: JsonValue,
    *,
    policy: InputPolicy,
    store: ContentStore,
    invocation_repository: ProductionInvocationRepository,
    invoke: JobInvoker,
) -> JobResult:
    """Decode and run one job request given as JSON data.

    A request that does not decode is rejected, echoing its key when one
    could be read.
    """

    try:
        request = decode_job_request(data)
    except JobRequestError as exc:
        return rejected_job_result(
            exc.error,
            idempotency_key=exc.idempotency_key,
        )

    return await run_invoke_job(
        request,
        policy=policy,
        store=store,
        invocation_repository=invocation_repository,
        invoke=invoke,
    )


async def run_job_content(
    content: str | bytes,
    *,
    policy: InputPolicy,
    store: ContentStore,
    invocation_repository: ProductionInvocationRepository,
    invoke: JobInvoker,
) -> JobResult:
    """Parse and run one job request given as JSON text or bytes.

    Content that is not a JSON job request is rejected, echoing its key when
    one could be read.
    """

    try:
        request = parse_job_request(content)
    except JobRequestError as exc:
        return rejected_job_result(
            exc.error,
            idempotency_key=exc.idempotency_key,
        )

    return await run_invoke_job(
        request,
        policy=policy,
        store=store,
        invocation_repository=invocation_repository,
        invoke=invoke,
    )


def recorded_job_result(
    key: str,
    *,
    request_digest: str,
    invocation_repository: ProductionInvocationRepository,
) -> JobResult | None:
    """Return what a key already recorded says about one request, if anything.

    No invocation under the key returns `None`. One recorded for the same
    request digest is replayed: its terminal result, or `incomplete`. One
    recorded for a different digest is a conflict.
    """

    invocation = invocation_repository.invocation_for_idempotency_key(key)

    if invocation is None:
        return None

    if invocation.idempotency is None or invocation.idempotency.request_digest != request_digest:
        return rejected_job_result(
            JobError(
                code=JobErrorCode.IDEMPOTENCY_CONFLICT,
                message=(
                    f"Idempotency key {key!r} was already used for a different request; "
                    "send a new key for a new request."
                ),
            ),
            idempotency_key=key,
        )

    result = invocation_repository.result(invocation.id)

    if result is None:
        return incomplete_job_result(
            invocation.id,
            idempotency_key=key,
        )

    return job_result_from_invocation(
        result,
        idempotency_key=key,
        replayed=True,
    )


__all__ = [
    "JobInvoker",
    "recorded_job_result",
    "run_invoke_job",
    "run_job",
    "run_job_content",
    "runtime_job_invoker",
]
