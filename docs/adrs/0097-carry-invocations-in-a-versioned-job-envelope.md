# ADR 0097: Carry Invocations in a Versioned Job Envelope

- Status: Accepted
- Date: 2026-10-31
- Decided in: #114

## Context

A production invocation is started today by `workflow invoke`, whose request
is spread across a positional workflow ID and the `--input`, `--input-file`
and `--media-type` options, and whose outcome is a process exit code plus
whatever the output format prints. That is right for an operator at a
terminal, and wrong for a program.

Three callers planned for 1.1 and after are programs: the queue worker, which
takes requests from SQS; Azathoth-MCP, which takes them from an agent; and the
UI. Each needs the same things the CLI never had to name:

- a request it can serialize, validate and log as one document;
- an outcome it can read without parsing human text or exit codes;
- a version, so a request written for one release is refused clearly by
  another rather than misread;
- a way to retry safely. SQS delivers a message at least once, an agent
  retries when a call times out, and a person double-clicks. Each must not
  start a second invocation, with a second bill, for one request.

If each caller invented its own request shape, the three would drift, and the
idempotency rule would be written three times.

## Decision

An invocation is requested and reported through a versioned **job envelope**:
one JSON request document and one JSON result document. It is a typed job
API, not a remote CLI: it carries no argv, options or output formats, and it
names exactly what an invocation needs.

Azathoth 1.1 ships one kind of job, `invoke`, at version `1`. The code lives
in `azathoth.jobs`, which depends on the workflow and input packages and not
on the CLI, so every entry point shares it.

### The request

```json
{
  "kind": "invoke",
  "version": 1,
  "idempotency_key": "order-4711-review",
  "workflow_id": "<UUID>",
  "input": {"uri": "file:///Users/you/change.json", "media_type": "application/json"},
  "caller_metadata": {"ticket": "OPS-12"}
}
```

- `kind` and `version` are required. `kind` is `invoke`; `version` is `1`.
- `idempotency_key` is required: 1 to 255 characters, with no control
  characters. It is otherwise opaque.
- `workflow_id` is the UUID of the workflow to invoke against its active
  production state.
- `input` is a workflow input source, an inline value or a reference (ADR
  0096). It is resolved under the policy of the entry point that received the
  request.
- `caller_metadata` is optional, a JSON object recorded with the invocation
  (ADR 0065). It defaults to `{}`.
- The shape is closed: any other key is refused.

### The result

```json
{
  "kind": "invoke",
  "version": 1,
  "idempotency_key": "order-4711-review",
  "status": "succeeded",
  "replayed": false,
  "invocation_id": "<UUID>",
  "result": {"verdict": "approve"},
  "error": null
}
```

`status` is one of four values:

| Status | Meaning | `invocation_id` | `result` | `error` |
| --- | --- | --- | --- | --- |
| `succeeded` | The invocation completed with a result. | set | the declared result | `null` |
| `failed` | The invocation completed with a production failure. | set | `null` | set |
| `rejected` | No invocation was recorded for this request. | `null` | `null` | set |
| `incomplete` | The key's invocation exists but has no result. | set | `null` | set |

A rejected request leaves no trace, so its key is still free; the same key
may be sent again once the request is fixed.

`incomplete` means the invocation was interrupted, or is still running in
another process. Nothing can yet finish it; resuming interrupted invocations
is a separate, planned decision.

`replayed` is `true` when the result reports an invocation that an earlier
request with the same key started, and nothing was run for this request. It
is `false` otherwise.

`error` is `{"code": <code>, "message": <text>, "metadata": {...}}`. The codes
are every production invocation error code (`workflow_not_deployed`,
`invalid_input`, `model_unavailable`, `no_approved_model_substitute`,
`tool_unavailable`, `workflow_execution_failed`, `timeout`), so a failed job
and a failed `workflow invoke` report the same code, plus four that only the
envelope produces:

- `invalid_request`: the request is not valid JSON, is not an object, or does
  not have the request's shape.
- `unsupported_version`: the kind is known, the version is not.
- `idempotency_conflict`: the key was already used for a different request.
- `invocation_incomplete`: the key's invocation has no result.

An unknown kind is `invalid_request` with `{"supported_kinds": ["invoke"]}` in
its metadata.

An input that cannot be resolved is `rejected` with `invalid_input`: as ADR
0096 decided, a reference that fails at the edge starts nothing.

### Versions

The result always speaks the responder's own kind and version. A request
whose `version` the responder does not support is rejected with
`unsupported_version` and `{"supported_versions": [1]}` in its metadata.
`kind` and `version` are read before the rest of the request is validated, so
a version-2 request is reported as an unsupported version, never as a list of
fields version 1 does not know.

A later version adds a new request and result model. It does not change what
version 1 means.

`idempotency_key` in the result echoes the request's key when the request
could be read far enough to find a valid one, and is `null` otherwise.

### Idempotency

Every invocation started through an envelope records its key and a **request
digest** with it.

The request digest is the lowercase hex SHA-256 of the request's canonical
JSON: its JSON-mode dump, with defaults filled in, keys sorted, no
insignificant whitespace, and `idempotency_key` left out. It digests the
request as given. A reference is digested by its URI and media type, not by
the content it names, so a replay needs neither the content nor the runtime.
Like the digests of ADR 0076, stored request digests are compared, never
recomputed.

Keys are global: one key names one invocation, whichever workflow it targets.
A request for another workflow under a used key is a conflict.

A request is handled in this order:

1. Read `kind` and `version`, then validate the rest. Any failure is
   `rejected`.
2. Compute the request digest, and look the key up.
   - The key is recorded with the same digest: report the recorded
     invocation, with `replayed: true`. A terminal result replays as
     `succeeded` or `failed`; no result yet is `incomplete`.
   - The key is recorded with a different digest: `rejected` with
     `idempotency_conflict`.
3. Resolve the input under the entry point's policy. A failure is
   `rejected` with `invalid_input`.
4. Invoke the workflow, recording the key and digest on the invocation
   before anything runs.

Failures replay. A key whose invocation failed, even with a transient code
such as `model_unavailable`, reports that failure on every retry. Trying
again means sending a new key. One key stands for one invocation, and its
outcome never changes.

Two requests racing with one key are settled by the store. The key is unique
across recorded invocations, so the second save fails, and that request looks
the key up again and reports what it finds, a replay or `incomplete`, without
running anything.

In SQLite, `production_invocations` gains nullable `idempotency_key` and
`request_digest` columns and a unique index on the key where it is not null.
An existing database gains the columns in place, keeping every invocation and
its sequence. Invocations started by `workflow invoke` record no key.

Keys never expire in 1.1. A key lives as long as its invocation, and nothing
removes invocation history yet. Expiry arrives with a retention policy, as a
separate decision.

### The CLI

```bash
azathoth job run request.json
azathoth job run - < request.json
```

`job run` reads one request from a file, or from standard input when given
`-`, and prints exactly one result envelope as JSON on standard output, and
nothing else. It exits with status 0 when the job `succeeded`, and 1 for every
other status. A file that cannot be read, or that is not JSON, still prints a
`rejected` envelope.

Its input policy is the CLI's: `file://` references only (ADR 0096). The
runtime, and with it any provider credential, is loaded only when a workflow
is actually invoked, so a replay, a conflict or a rejection needs none.

`job run` does not stream step records. A job is a request and a response;
live progress for jobs is a separate decision.

`invocation show` names the key and request digest of an invocation that has
them.

## Consequences

### Positive

- The queue worker, Azathoth-MCP and the UI share one request, one result and
  one idempotency rule, written once in `azathoth.jobs`.
- A retried request, from SQS redelivery, an agent's timeout or a person,
  never starts a second invocation.
- A program reads the outcome as data: a status, a result, and a stable error
  code shared with `workflow invoke`.
- A request written for a later version is refused by name, with the versions
  that would be accepted.
- Replays, conflicts and rejections cost nothing: no provider credentials, no
  model calls.

### Negative

- A failed invocation cannot be retried under its key, even when the cause
  was transient. Callers retrying failures must mint new keys.
- An interrupted invocation reports `incomplete` under its key until resume
  lands, and nothing can finish it in the meantime.
- A reference whose content changed is replayed under its key with the result
  of the original content.
- Keys accumulate with invocation history, and nothing removes them yet.
- `caller_metadata` is part of the digest, so a retry that changes only its
  metadata is a conflict.

## Alternatives Considered

### A remote CLI

Rejected. Carrying argv in a message would tie every program to the CLI's
options, output formats and exit codes, and would let a message ask for
whatever any CLI command does. The envelope names one operation, and adding
one is a deliberate change.

### A separate jobs table

Rejected for 1.1. A table of keys pointing at invocations would add a second
record that can disagree with the first, and a second write that can fail
between them. The key belongs to the invocation it names, so it is recorded
on it, in the same row and the same write.

### Digest the resolved content

Rejected. A replay would have to read the reference again, needing the file
or the bucket to still exist, and every retry would pay for a read. The key
names the caller's intent, which is the request it sent.

### Optional keys

Rejected for version 1. A request without a key cannot be retried safely,
which is the envelope's reason to exist. A caller that does not want a key
uses `workflow invoke`.

### Keys scoped to a workflow

Rejected. One key naming different invocations on different workflows makes
a caller's mistake, the same key sent for two jobs, look like success.

### Let failed invocations be retried under the same key

Rejected. The key's outcome would then change over time, and two racing
retries could both run. A new key for a new attempt keeps one key, one
invocation.
