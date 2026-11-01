# Jobs

`azathoth.jobs` is the versioned job envelope (ADR 0097): one JSON request
and one JSON result for a production invocation. It is the typed API that
programs share, the queue worker, Azathoth-MCP and the UI among them, and
`azathoth job run` is its command-line entry point.

It is a typed job API, not a remote CLI. A request names one operation and
exactly what it needs; it carries no argv, options or output formats.

```python
from azathoth.jobs import (
    InvokeJobRequest,
    JobResult,
    JobStatus,
    decode_job_request,
    job_request_digest,
    run_job,
    run_job_content,
    runtime_job_invoker,
)
```

## Requests

Azathoth 1.1 knows one kind of job, `invoke`, at version `1`:

```json
{
  "kind": "invoke",
  "version": 1,
  "idempotency_key": "order-4711-review",
  "workflow_id": "d2000000-0000-4000-8000-000000000010",
  "input": {"value": {"title": "Rename total to order_total"}},
  "caller_metadata": {"ticket": "OPS-12"}
}
```

`InvokeJobRequest` is closed: any other key is refused.

- `idempotency_key` is required: 1 to 255 characters, with no control
  characters, and otherwise opaque.
- `input` is a workflow input source, an inline value or a reference (see
  the inputs package). It is resolved under the policy of the entry point
  that received the request.
- `caller_metadata` is optional and defaults to `{}`.

`decode_job_request(data)` reads `kind` and `version` before the rest of the
request, so a request for a later version is reported as an unsupported
version, never as a list of fields this version does not know.
`parse_job_request(content)` does the same from JSON text or bytes, and
refuses `NaN` and the infinities. Both raise `JobRequestError`, which carries
the `JobError` to report and the request's idempotency key when a valid one
could be read.

## Results

```json
{
  "kind": "invoke",
  "version": 1,
  "idempotency_key": "order-4711-review",
  "status": "succeeded",
  "replayed": false,
  "invocation_id": "<INVOCATION_ID>",
  "result": {"verdict": "approve"},
  "error": null
}
```

`JobResult` always speaks this release's kind and version. Its status says
which fields are set, and the model refuses any other combination:

| Status | Meaning | `invocation_id` | `error` |
| --- | --- | --- | --- |
| `succeeded` | The invocation completed with a result. | set | `null` |
| `failed` | The invocation completed with a production failure. | set | a production code |
| `rejected` | No invocation was recorded for this request. | `null` | a rejection code |
| `incomplete` | The key's invocation exists but has no result. | set | `invocation_incomplete` |

`JobErrorCode` holds every `ProductionInvocationErrorCode` value, so a failed
job reports the same code as a failed `workflow invoke`, plus four codes only
the envelope produces: `invalid_request`, `unsupported_version`,
`idempotency_conflict` and `invocation_incomplete`. A request is rejected for
one of the first three, or for `invalid_input` when its input cannot be
resolved.

`replayed` is `true` when the result reports an invocation that an earlier
request with the same key started, and nothing was run for this request.

## Idempotency

`job_request_digest(request)` is the lowercase hex SHA-256 of the request's
canonical JSON: its JSON-mode dump with defaults filled in, keys sorted, no
insignificant whitespace, and the idempotency key left out. A reference is
digested by its URI and media type, never by its content.

`run_invoke_job` handles a request in this order:

1. Digest it and look its key up. A key recorded with the same digest
   replays its invocation, as `succeeded` or `failed`, or `incomplete`; a key
   recorded with a different digest is an `idempotency_conflict`. Nothing is
   resolved or run.
2. Resolve the input under the entry point's policy. A failure is `rejected`
   with `invalid_input`, and records nothing, so the key stays free.
3. Invoke the workflow, recording the key and digest on the invocation before
   anything runs.

Keys are global across workflows, failures replay like successes, and keys
never expire in 1.1. Of two requests racing with one key, the store saves
exactly one; the other reports what it finds instead of running.

`run_job(data)` and `run_job_content(content)` decode first, and turn a
request that does not decode into a `rejected` result.

## Invokers

`run_invoke_job` invokes through a `JobInvoker`, so it never composes a
runtime itself. `runtime_job_invoker(load_runtime, ...)` binds one to the
production invocation service and calls `load_runtime` only on the first
invocation:

```python
invoke = runtime_job_invoker(
    lambda: load_runtime(configuration),
    invocation_repository=invocations,
    run_repository=runs,
    invocation_run_repository=invocation_runs,
)

result = await run_job_content(
    content,
    policy=CLI_INPUT_POLICY,
    store=SQLiteContentStore(database),
    invocation_repository=invocations,
    invoke=invoke,
)
```

A replay, a conflict or a rejection therefore loads no provider state and
needs no credentials.
