# ADR 0137: A Client for the Service API

- Status: Accepted
- Date: 2026-11-22

## Context

ADR 0136 put the service API on a remote's routes: `POST
/v1/calls/<name>`, its arguments read and its result written by each
call's own signature. Nothing in Azathoth called those routes. The command
line's `--remote` and the editor's remote screens are to work on a remote
as they work on a local instance, so they need a client that is the
service API, not a second one to learn.

Four things had to be decided. What a client is, so code written for a
local instance runs against a remote unchanged. How a refusal travels
back, since a route answers only a message and a code, and a caller
catches errors by their kind. What a client does with a call a remote does
not yet run, the jobs. And how a client is reached by the names an
instance gives its remotes, each with its own token.

## Decision

### An instance is an `Instance`

`azathoth.api.Instance` is a Protocol: the context manager, `closed`, the
thirteen collections of calls, `describe` and `close`. `Azathoth`
satisfies it as it is. It has no `remote` or `remotes`, which name an
instance's own remotes and which a remote never serves (ADR 0127).

`api.connect(url)` returns a `ConnectedInstance`, which satisfies it too.
Its collections are typed as a local instance's, `Workflows` and the
rest, so an editor and mypy see exactly the calls and arguments a local
instance takes; each is a proxy that sends every call to the remote. A
call's arguments are bound to the local method's own signature, as Python
binds them, and only those given are sent, so the rest take the call's
defaults at the remote. Each call carries the local signature and
docstring. Its result is read by the call's `CallSignature`, as the
remote wrote it, so it is the value the local call returns.

A call is sent by a `CallTransport`, over the HTTP client the remote
protocol's client uses, with the remote's token as a bearer token.

### A refusal travels back as its error

A service route refuses an `ApiError` with a `Refusal`: its message, its
code, and in `kinds` the code of its kind and of each kind it descends
from, nearest first. A `ModelInUseError` carries its `dependents`.
`azathoth.remote.refusals` reads one back as the nearest kind this
Azathoth knows, with the remote's message, so a caller catches
`PermissionDeniedError` or `NotFoundError` through a remote as it does
locally, and a newer remote's new kind of `NotFoundError` is still a
`NotFoundError` to an older client.

A refusal of no kind the client knows, such as `unauthenticated` or
`plugin_error`, is a `RemoteRefusedError` with the `status` and the
`refusal` code it was refused with. A 503 of none, such as
`audit_unavailable`, is a `RemoteUnavailableError`, a `RemoteRefusedError`
too, so a caller that tries again later catches it alone. A server that
answers as no remote does, or a result that is not the call's, is a
`RemoteUnreachableError`, as it is for a push or a pull.

### Jobs are refused before anything is sent

The eight jobs take a callback for their events, which cannot travel. A
connected instance refuses each before sending anything, as a
`RemoteRefusedError` with status 501 and refusal `job`, as the remote
would. Running them on a remote's workers, and their events, come with
the workers.

### A named remote is connected to with its own token

`connect` reads the token given, or the one `AZATHOTH_REMOTE_TOKEN`
holds. `instance.remote(name).connect()` connects to a remote an instance
named with the token its own variable holds, as a push to it does. Both
refuse a URL or a missing token as reaching a remote does, and the
connection needs nothing of the instance that named the remote once it is
made.

## Consequences

- Code written for an `Instance` runs against a local database or a
  remote unchanged, and a refusal through a remote is caught as the same
  error.
- Each call is one request. Code that makes many small calls locally
  makes as many requests to a remote.
- A connected call may raise `RemoteUnreachableError` and
  `RemoteRefusedError` beyond what the call's docstring names; this ADR
  and the service API's README say so once rather than every docstring.
- A connected collection is typed as the local class but is not one:
  `isinstance` says no, and only its calls are attributes.
- An unexpected failure at the remote is a `RemoteRefusedError` with
  status 500, not the exception the local call would have raised.
- A client decides from its own catalog that a call is a job, so until it
  is upgraded it refuses a job even of a remote that runs them.
- A refusal body grows `kinds`, and `dependents` for `model_in_use`; a
  client that reads only `error` and `code` reads it as before.

## Alternatives Considered

### Client classes written for each collection

A `RemoteWorkflows` and the like would be real classes, but the 66 calls
a remote answers written again and kept in step with them, as ADR 0136
declined for routes.
The proxies are made from the calls, and a test holds every served call to
being on a connected instance with the local signature.

### Rebuilding an error from its code alone

A client knowing only its own codes would read a newer remote's new kind
as a bare refusal, and a caller catching its ancestor would miss it.
Naming the ancestry costs a few codes in a refusal.

### Every refusal as a `RemoteRefusedError`

One kind for everything a remote refuses would make a caller parse
messages to tell a missing workflow from a refused one, which a local
instance never asks of it.

### Sending a job for the remote to refuse

The client knows a job by its catalog, and its callbacks cannot be
written, so sending one would only ask the remote to refuse it.
