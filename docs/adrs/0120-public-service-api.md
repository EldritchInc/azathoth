# ADR 0120: Public Service API

- Status: Accepted
- Date: 2026-11-08

## Context

Azathoth is driven three ways: the command line, azathoth-mcp (ADR 0111),
and, from 1.4, a local editor whose browser talks to a small Python server.
The CLI composes the engine itself, module by module, and azathoth-mcp
reaches past it into the runtime and the job layer. A third caller written
the same way would be a third copy of how a workflow is found, invoked and
reported, each drifting from the others, and the editor would depend on
internal models that 1.x does not promise to keep.

The editor is a separate distribution in a separate repository, released on
its own schedule against released Azathoth. It needs one surface it can
depend on, whose values it can send to a browser as they are, and whose
errors it can map to responses without reading their messages.

## Decision

### One in-process, synchronous facade

`azathoth.api` is the service layer every caller uses. `open(database)`
opens the instance one database holds, named as `AZATHOTH_DATABASE` names
it, and returns an `Azathoth`, best used as a context manager. Calls run on
the caller's thread and return when they are done. A caller that needs
concurrency, such as the editor's server, runs calls on worker threads; the
engine is synchronous throughout, and the API does not pretend otherwise.

Opening never creates or changes a database. A missing SQLite file is
refused, as is a PostgreSQL database without this Azathoth's schema; both
messages say to run `azathoth init`, which `initialize(database)` does
through the API. Once closed, an instance refuses every call.

The facade groups its operations by what they act on, as namespaces of the
instance: workflows, tools, benchmarks, models, portfolio, runs and
invocations. `open` also takes the telemetry that traces runs and
invocations, and the S3 location that keeps resolved content, as the
command line's environment gives them.

The API caches nothing a run depends on. Every run and invocation asks the
providers what they serve: a missing fixed model stops a run before it
starts, and which substitute a production state may use depends on what is
available now. How a client caches, or which of its threads calls, is the
client's to decide.

### The API returns its own models

Every value the API returns is an `ApiModel`: a frozen pydantic model that
refuses unknown fields and is its own JSON. None of them is an internal
model, so the engine can change beneath the API while what callers read
stays put. A field whose value Azathoth does not know, such as a model's
context length when its provider does not publish one, is `None`, and its
description says so. A value with an equivalent `azathoth` command carries
that command, so no caller builds command lines itself.

### Errors carry codes

Every error the API raises on purpose is an `ApiError`, and each kind
carries a `code`, a short stable name such as `instance_not_found`. Messages
are exact and tested. Errors the engine raises in its own terms, such as a
database without its schema, are raised again as the API's own, with the
original as their cause.

### Runs and invocations

`runs.run` is `azathoth workflow run`: a workflow's latest revision, as
configured. `runs.invoke` is `azathoth job run`: its active production
state, under an idempotency key, so the same request replays its outcome or
resumes it, and another request under the key is rejected. A workflow that
is not in production, or that fails, is an invocation's outcome rather than
an error, as it is in a job's result.

### Runs report through a callback

Running a workflow takes an optional `on_event` callback and calls it, on
the run's thread, with each typed event as it happens: the run starting,
each step starting and finishing, each change to the context, and the run
finishing. A context change carries the values a finished step declared,
by name, never the whole context. The call still returns the run's result
and raises its errors as any call does.

A callback must be quick. One that raises is detached for the rest of the
run and its failure is recorded as a warning on the result: a broken
display never fails a run. A run is stopped by a cancellation token passed
with it, never by abandoning an iterator. Cancelling stops the run where it
is, as Ctrl-C stops `azathoth workflow run`: a running tool process is
killed, the run's lease is released, nothing is kept as a finished run, and
its journal can be resumed.

Events on the caller's own instance carry the values they report. The rule
that a shared instance shows only aggregates applies to what a remote
serves, not to a caller watching its own runs.

### Provisional until 1.4.0

The API is provisional while 1.4 is in pre-release, and may change between
pre-releases. `API_STABILITY` says which, and every instance reports it. At
1.4.0 the 1.x compatibility promise grows to cover `azathoth.api`; the rest
of the Python API stays outside it.

### The callers move onto it

azathoth-mcp is a client like any other: each tool call is `runs.invoke`
on a worker thread, and `get_invocation` reads `invocations.get`, while the
server keeps its own rules of who may call and read what. A call the client
cancels cancels its invocation. The server no longer keeps a runtime between
calls, which amends ADR 0111: each call asks the providers what they serve,
as `azathoth job run` does, and sees every import and authorization at once.
The CLI's commands that the API covers call it, and its other commands move
as the API grows to cover them.

### Contracts run on both databases

`tests/api` holds the API's contract tests. Each runs on SQLite, and on
PostgreSQL wherever a server is named, in CI's `postgres` job and
`make postgres-test`, so a caller sees the same API whichever database the
instance keeps.

### The public repository names no private code

Eldritch's commercial distributions live in private repositories. The
public repository never imports them, depends on them, or names them: a test
that `make check` runs fails if any file, or any file's path, does. Public
decision records describe only interfaces a private distribution could
implement.

## Consequences

- The CLI, azathoth-mcp and the editor share one way to find, invoke and
  report on workflows, so they cannot drift apart.
- The editor depends on a surface 1.x will promise to keep, and sends its
  values to the browser unchanged.
- Each value the API returns is a copy of what the engine holds, which costs
  a conversion per call.
- A caller that wants a stream of events adapts the callback itself; the
  editor's server does so with a queue, and nothing else pays for threads.
- Every new contract test runs twice where a PostgreSQL server is named.

## Alternatives Considered

### Return the engine's own models

Rejected. Every internal model would become part of the promise, and the
engine could not change one without breaking the editor.

### A generator of events

Rejected. Yielding events while a run executes means either rewriting the
runner as a generator or running each invocation on a thread inside the
API. An abandoned generator would leave a run holding its connection and
lease, errors and results would have to cross threads, and every caller
would pay for threads only one needs.

### An asynchronous API

Rejected. A client that runs in an event loop, as azathoth-mcp does, calls
the API from a worker thread, and so chooses its own concurrency; the API
does not choose it for every client. Each call runs its workflow on an
event loop of its own, so a run steps through its workflow exactly as it
does from the command line, whichever thread called.

### Move every CLI command at once

Rejected for 1.4. The commands the API does not cover yet keep working as
they are, and move when it does.
