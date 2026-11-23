# ADR 0136: The Service API Over HTTP

- Status: Accepted; amended by ADR 0137, ADR 0138
- Date: 2026-11-22

## Context

ADR 0127 decided that a remote serves the service API, one route for each
call, under `/v1`, so the people of a team work on one Azathoth from the
command line and the editor. ADR 0134 put in code what each call asks a
remote's policy and tells its audit, and ADR 0135 let a remote answer
requests together. What was left was the routes themselves: what a request
and an answer look like, who a change is recorded as, what is checked when,
and what the audit is told and when.

ADR 0127 left four questions open. The shape of a route: a path written for
each call is 79 shapes to keep in step with the calls. The calls that run
for minutes, a run, a benchmark or an optimization: they take callbacks for
their events that cannot travel. Who is the author of a change made through
a remote: the server is not the person. And when the audit is told: a
remote that tells its audit after acting has acted for anyone whose event
the audit then loses.

## Decision

### One route for each call, read from the call

Every call is `POST /v1/calls/<name>`, such as `POST /v1/calls/workflows.get`.
The body is a JSON object of the call's arguments by name, and the answer
is its result as JSON. `azathoth.remote.calling` reads each call's
parameters and result from its method on `Azathoth`, and pydantic reads and
writes them, so no route is written by hand: a call added to the service
API is served as it is. Arguments that are not the call's are refused 400
saying where. A `bytes` value, a run's file, travels in base64. A client
writes neither unset arguments nor those given as their default, so a
remote's defaults are always the call's own.

Every call is posted, reads too, so IDs and documents travel in a body
rather than in a URL that access logs keep. The path cannot collide with
the protocol's routes, and a client builds every request from a call's
name.

`GET /v1/service` says what a remote serves: the Azathoth serving it, the
service API's stability, the protocol, and the edition the policy names
with its detail. `GET /v1/permissions` tells any caller the remote knows
every action and whether the policy allows it, and why not; `POST
/v1/permissions` asks the same of up to a hundred resources. A client asks
before it shows what acts; every route still asks the policy itself.

### Refusals with a code

A service route refuses with `{"error": "<MESSAGE>", "code": "<CODE>"}`.
An `ApiError` keeps its own code and is answered with the status its kind
is given, every kind the service API defines having one: what the caller
sent is 400 or 422, what the policy refuses 403, what is not there 404, a
clash 409, a provider, an MCP server or another remote that failed 502, and
the remote's own database or configuration 503. A refusal the remote makes
itself has the code of its status, `unauthenticated` for 401. The
protocol's routes refuse as protocol 1 always has, with no code.

### Jobs wait for the workers

The eight calls that take a callback for their events are jobs:
`runs.run`, `runs.try_step`, `runs.invoke`, `runs.resume`,
`invocations.resume`, `benchmarks.run`, `benchmarks.compare` and
`optimization.optimize`. A remote runs them on its workers, as ADR 0107
runs a queued job, rather than while a request holds a connection for
minutes. Until it does, each is answered 501 with the code `job`. A test
holds the jobs to exactly the calls that take a callback.

### The caller is the author

Each caller is answered by an instance of their own, made the first time
they call, over the repositories the remote shares, with their principal's
name as its author. What a person imports, creates or authorizes through a
remote is recorded as theirs. None of these instances is closed, since
closing one would close the database the others serve. A model provider is
asked what it serves on every call that needs it; which providers are on,
and their keys, are read when `azathoth remote serve` starts.

### What a call asks, and when

A call asks the policy each of its actions about the resource its argument
names, as `<kind> <ID>`. Each condition the catalog names has one check,
told from the arguments before the call runs or from its result before
that is sent: a call that changes something is always checked before, so
nothing is changed for a caller the policy refuses, and a restricted read
is checked from what was read, and a refusal sends none of it. A listing
asks once, then about each thing it returns, and leaves out what is
refused: a listing of nothing the caller may see is empty, not refused. A
push carrying a process tool asks `import_process_tool` for each such tool,
as importing one does.

### The audit is told first

A remote tells its audit before it acts, and before it sends what it read.
Each call tells each kind it may record whose action it asked, so a process
tool's import tells both imports, and a restricted read `restricted_read`
beside what the call did; a read of nothing restricted tells nothing. A
call that told the audit and then fails is followed by `request_failed`, a
new kind, naming the call and the failure's code. An audit that cannot be told stops the request with 503
and `audit_unavailable`: nothing is changed and nothing is sent. A refusal
is answered whether or not the audit can be told of it.

The protocol's routes follow the same order: a push is told, with how many
revisions it offers, before anything is received, and `request_failed`
follows one that is then refused or diverges. `azathoth remote token
create` and `revoke` tell the audit the remote serves with, as
`operator:<author>`, before the token changes.

### Installing the standard tools

ADR 0134 left installing the standard tool library with an action and no
call. `tools.install_standard` is that call, asking `install_standard_tools`,
and `init`, `tool install-standard`, `api.initialize` and the call install
the library one way.

## Consequences

- A remote's people can do over HTTP everything the service API does,
  except the eight jobs, as its owner allows; F's client speaks exactly
  these routes, built from the same signatures.
- A team tier's policy decides every call of every person, about each thing
  they name or list, and its audit is told of every change before it is
  made; an audit that is down stops the remote changing anything.
- A push's audit says what it offered, not what it received, since the
  event is told before receiving.
- A change made through a remote is recorded as the caller's, under their
  principal's name.
- Turning a provider on, or changing its key, takes restarting `azathoth
  remote serve`.
- `describe` through a remote says where the remote's database is, as it
  does locally, without a password.

## Alternatives Considered

### A path written for each call

`GET /v1/workflows/{id}` and the like read well, but are 79 shapes to write,
test and keep in step with the calls, and a client would need each written
again. One shape read from the call keeps the routes and the calls one
thing.

### Running jobs while the request waits

A run answered inline would hold a pooled connection and a thread for as
long as it ran, and a dropped connection would lose its events. The
workers are made for it; the routes exist and are decided and audited
until then.

### The server as the author

Recording every change as the server's would lose who made it, which a
team's audit and history are for.

### Telling the audit after acting

Telling it after keeps a push's received count, but a remote whose audit
then fails has acted unaudited, which a tamper-evident audit is there to
prevent. Telling it first, and following a failure with `request_failed`,
keeps the audit a record of everything attempted.

### One event for a process tool's import

Recording only `process_tool_imported` would say less: the two events say
that a tool was imported, and that it was one of high privilege, which an
audit can then be searched for alone.
