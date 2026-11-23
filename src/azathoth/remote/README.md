# Remote

`azathoth.remote` moves durable documents between instances: a client
pushes workflows, tools and benchmarks to a remote, and pulls them back
(ADR 0124). This package holds what both sides agree on; it opens no
connection itself.

```python
from azathoth.remote import (
    Capabilities,
    PushBundle,
    RevisionRecord,
    closure,
    load_seams,
    require_protocol,
)
```

## The Protocol

A remote and its client speak remote protocol `PROTOCOL_VERSION`, 1. Before
anything travels, a client reads the remote's `Capabilities`: the protocol,
its Azathoth version and schema version, its edition (`community` unless a
plugin names another), the plugin serving each seam a plugin serves, and
whether it accepts restricted data. Either side refuses another protocol
with `require_protocol`, naming both:

```text
The remote speaks remote protocol <PROTOCOL>, and this Azathoth speaks remote protocol 1; run versions of Azathoth that speak the same protocol on both.
```

A push bundle is at most `MAX_PUSH_BYTES`, 64 MB, and one content blob at
most `MAX_CONTENT_BYTES`, 10 MB.

## Records

A revision travels as a `RevisionRecord`: its lineage, revision digest,
parent digest, content digest, author, and its document as JSON. A record is
checked without the model that made its document, so two versions of
Azathoth that speak one protocol agree on it: the document names the
record's lineage, its `json_digest` is the content digest, and the revision
digest is the digest of the lineage, content and parent (ADR 0122). A record
that disagrees with its digests is refused:

```text
Revision <DIGEST> holds a document that is not one of workflow <WORKFLOW_ID>'s.
Revision <DIGEST> of workflow <WORKFLOW_ID> holds content <HELD>, not its content digest <CONTENT_DIGEST>.
Revision <DIGEST> of workflow <WORKFLOW_ID> is not the digest of its lineage, content and parent, which is <COMPUTED>.
```

A benchmark record is as sensitive as its most sensitive case; a workflow or
tool holds no run's data, so it is internal (ADR 0123). A `ContentRecord`
is content a pushed benchmark's cases hold, labelled as the most sensitive
of them, since content carries no label of its own.

A `PushBundle` carries revisions, each lineage's oldest first and each
building on the one before it, and the content they hold. A lineage's first
revision in a bundle builds on one the remote holds, or on none. Before
pushing, a client offers digests in a `MissingRequest`, and the remote
answers with the `MissingResponse` of those it lacks, so a push carries only
what is missing.

## Closures

`closure(roots, workflows=..., tools=..., benchmarks=...)` gathers what a
push of some lineages sends: each one's latest revision with the revisions
it was reached by, oldest first, and what it needs at the remote. A
workflow needs the tool versions its tool steps match here, and the child
workflows its `run_workflow` step's `call`, or its `map_workflow` or
`loop_workflow` step's `settings`, names as a constant. A benchmark needs
the content its cases hold. Dependencies come before the documents that
need them, and each lineage once.

Production state and the model portfolio are each instance's own, so no
closure holds them. What a closure cannot gather is named in `unresolved`,
one sentence each:

```text
This instance holds no workflow <WORKFLOW_ID>.
Step <STEP_ID> of workflow <WORKFLOW_ID> requires tool <NAME> <VERSION>, which this instance does not hold.
Step <STEP_ID> of workflow <WORKFLOW_ID> runs workflow <CHILD_ID>, which this instance does not hold.
Step <STEP_ID> of workflow <WORKFLOW_ID> names its child workflow only when it runs, so no child is pushed with it.
Revision <NUMBER> of workflow <WORKFLOW_ID> no longer serializes to its content digest <CONTENT_DIGEST>, so it cannot be pushed.
```

A requirement without a version names its tool `of any version`, and needs
every version held. A revision that no longer serializes to its digest was
imported by an older Azathoth whose model dumped it differently; it stays
here, and is not pushed.

## Receiving

`receive(bundle, workflows=..., tools=..., benchmarks=..., content=...,
accepts_restricted=...)` saves the revisions of a bundle that are not held.
It checks every one first, and refuses the bundle, saving none of it, when
one fails:

- this Azathoth must read each document as the content its digest names;
- the content each benchmark case holds must be held already, since content
  is sent before the revisions that hold it;
- each lineage's first new revision must build on the latest one held.

A remote moves only forward, so a push whose lineage has diverged is
refused, and its author pulls first. A pull, `fork=True`, saves a diverged
lineage's revisions on the revision they build on, forking it, and its
`ReceiveReport` names each lineage it forked. A revision already held is
skipped, so a bundle sent again changes nothing, and each revision is
numbered by the instance that saves it.

```text
Workflow <WORKFLOW_ID> has diverged: its latest revision here, <LATEST>, is not the one revision <DIGEST> builds on. Pull first, then push again.
Revision <DIGEST> of workflow <WORKFLOW_ID> builds on <PARENT>, which is not held here; send the revisions before it too.
Revision <DIGEST> of workflow <WORKFLOW_ID> begins its history, but another history of it is held here.
Revision <DIGEST> of workflow <WORKFLOW_ID> is not a workflow document Azathoth <VERSION> reads: <ERROR>.
Azathoth <VERSION> reads revision <DIGEST> of workflow <WORKFLOW_ID> as content <READ>, not <CONTENT_DIGEST>; send it from an Azathoth that reads it as its digest names.
Content <CONTENT_DIGEST>, which revision <DIGEST> of benchmark <BENCHMARK_ID> holds, is not held here; send it first.
```

`receive_content` keeps one blob, labelled as its most sensitive case,
after checking its size and that its bytes are its digest:

```text
Content <CONTENT_DIGEST> is <SIZE> bytes; a remote accepts content of at most 10485760 bytes.
Content sent as <CONTENT_DIGEST> is <HELD>.
```

A remote not started to accept restricted data refuses a bundle or content
that holds any (ADR 0123):

```text
This push carries restricted data, and this remote does not accept restricted data. Its operator accepts it by starting the remote with `azathoth remote serve --accept-restricted`.
Content <CONTENT_DIGEST> is restricted, and this remote does not accept restricted data. Its operator accepts it by starting the remote with `azathoth remote serve --accept-restricted`.
```

## Seams

A remote asks three seams about every request: its `Authenticator` who the
caller is, from the `Authorization` header; its `Policy` whether that
`Principal` may do the `Action` they ask; and its `AuditSink` to record each
`AuditEvent`. The core fills each one: the tokens it issues authenticate,
`OwnerOnlyPolicy` lets only the owner do anything, and `NoAuditSink`
records nothing. Anyone else is refused:

```text
<PRINCIPAL> may not <ACTION> on this remote: only its owner may.
```

A plugin replaces a seam with an entry point in the `azathoth.remote` group
named `auth`, `policy` or `audit`, whose object is a factory taking no
arguments:

```toml
[project.entry-points."azathoth.remote"]
policy = "example_plugin:make_policy"
```

`load_seams(default_authenticator=...)` reads the installed entry points,
and returns the `Seams` a remote serves with, which tell its capabilities.
A remote does not start with plugins it cannot use:

```text
Two plugins fill the remote's <SEAM> seam, <FIRST> and <SECOND>; uninstall one of them.
Remote plugin <PLUGIN> names the seam '<NAME>'; a remote's seams are auth, policy and audit.
Remote plugin <PLUGIN> gave the <SEAM> seam an instance of <TYPE>, which is not <KIND>.
```

### Writing a Plugin

Within 1.x, a plugin may build on these names, and on nothing else in
Azathoth; each grows only by additions (ADR 0134):

- `azathoth.remote.seams`: `Principal`, `Action`, `HIGH_PRIVILEGE_ACTIONS`,
  `Decision`, `AuditEvent`, `AuditEventKind`, `Authenticator`, `Policy`,
  `AuditSink` and `RemotePluginError`.
- `azathoth.api.calls`: `SERVICE_CALLS`, `ServiceCall` and `service_call`,
  which say, for every call of the service API, what a remote asks its
  policy and tells its audit.
- `azathoth.persistence`: `Database`, `Session`, `Table`, `Dialect`, `Row`,
  `Parameter`, `InitializationOutcome`, `PersistenceError`, `IntegrityError`,
  `open_database`, `run_backfills`, `database_location`, `require_text` and
  `require_integer`. Every error the database raises is a
  `PersistenceError`.
- `azathoth.persistence.repositories`: `open_repositories` and
  `postgres_database`, which shares the process's pool of connections to a
  PostgreSQL database with the core.
- `azathoth.remote.tokens`: `TOKEN_PREFIX`, `RemoteToken` and
  `RemoteTokenRepository`, the owner's tokens.
- `azathoth.revisions`: `Author`, `AuthorError` and `resolve_author`, which
  name whoever runs a command as the core names an author.

A factory takes no arguments, so a plugin finds the remote's database with
`database_location()`, as `azathoth remote serve` does. Its tables are its
own, named apart from the core's, and it records their version itself:
`Database.initialize` records the core's schema version, so a plugin that
called it could mark a database the core never initialized as initialized.
A factory that cannot serve raises `RemotePluginError`, whose message the
remote prints before it stops.

A remote answers requests together, and calls its seams from the threads
it answers them on, up to eight at once (ADR 0135), so each seam must be
safe to call from several threads at once: keep no state between calls
that two threads could change together, or guard it with a lock. A factory
runs once, when the remote starts, and what it makes serves every request.
The core's own fillers keep no state, and each of their reads is a
read-only transaction of its own. An audit must keep every event, even when
two arrive together. An authenticator returns `None` for a header that
names no one it knows, rather than raising.

A policy names its `edition`, and may say more of it with an
`edition_detail` property: one printable line of at most 200 characters,
such as who the edition is licensed to, read afresh each time. A remote
shows both and never acts on either, since any plugin may name any edition;
what a caller may do is the policy's `decide` alone. The capabilities do not
change, since clients before 1.6 refuse a field they do not know.

## The Server

`azathoth.remote.server` serves the protocol and the service API over HTTP
with Starlette, the `remote` extra, so nothing else in Azathoth imports it.
`RemoteServer(...).app()` is the application `azathoth remote serve` runs
with uvicorn:

| Route | Action | Answers |
| --- | --- | --- |
| `GET /health` | | `{"status": "ok"}`, with no token |
| `GET /v1/service` | read capabilities | the `ServiceDescription` |
| `GET /v1/permissions` | | the caller's `PermissionsResponse` on the remote |
| `POST /v1/permissions` | | the `ResourcePermissionsResponse` to a `PermissionsRequest` |
| `POST /v1/calls/{name}` | the call's own | the call's result |
| `GET /v1/jobs` | | the caller's own jobs, newest first, each a `JobSummary` |
| `GET /v1/jobs/{job_id}` | `read_runs`, for another's | the `JobView`: the job, and its result or refusal |
| `POST /v1/jobs/{job_id}/cancel` | the job's call's, for another's | the `JobSummary`, once the job is asked to stop |
| `GET /v1/jobs/{job_id}/events` | `read_runs`, for another's | the job's events as server-sent events, then the `JobView` it ended as |
| `GET /v1/capabilities` | read capabilities | `Capabilities` |
| `POST /v1/missing` | push | the `MissingResponse` to a `MissingRequest` |
| `PUT /v1/content/{digest}` | push | the digest kept |
| `GET /v1/content/{digest}` | read content | the content's bytes |
| `POST /v1/push` | push | the `ReceiveReport` of a `PushBundle` |
| `POST /v1/pull` | pull | the `PullResponse` to a `PullRequest` |
| `POST /v1/heads` | pull | the `HeadsResponse` to a `HeadsRequest` |
| `GET /v1/portfolio` | read portfolio | the `PortfolioResponse` |
| `POST /v1/credentials` | push | the `CredentialsResponse` to a `CredentialsRequest` |

A content upload names its label in `X-Azathoth-Sensitivity`, internal
when absent. Every route but `/health` asks the authenticator who the
caller is, and the policy whether they may do the route's action; a push
asks again for each lineage it carries, a pull for each it asks for, and a
content route for its digest; a push carrying a process tool asks
`import_process_tool` for each, as importing one does. A refusal is JSON,
`{"error": "<MESSAGE>"}`, and a service route's adds a code, `{"error":
"<MESSAGE>", "code": "<CODE>"}`:

| Status | Refusal |
| --- | --- |
| 400 | A malformed request, another protocol, a path naming no digest, or arguments that are not the call's |
| 401 | No token the remote knows |
| 403 | The policy refuses it, or restricted data the remote does not accept |
| 404 | Content the remote does not hold, a call it does not serve, or what a call names that is not there |
| 409 | A push whose lineage has diverged, or a call that clashes with what is held |
| 413 | A body larger than the remote accepts |
| 422 | A push or content the receiving checks refuse, or a document a call refuses |
| 500 | A plugin that failed, `plugin_error` |
| 501 | A job, `job`, which a remote does not run yet |
| 502 | A provider, an MCP server or another remote a call needs that failed |
| 503 | An audit that could not be told, `audit_unavailable`, or the remote's own database or configuration |

```text
This remote does not know the token given. Send one its owner created with `azathoth remote token create`, as `Authorization: Bearer <TOKEN>`.
```

### Calls

Every call of the service API but those that name an instance's own
remotes is `POST /v1/calls/<NAME>`, such as `POST
/v1/calls/workflows.get` (ADR 0136). The body is a JSON object of the
call's arguments by name, empty for none, and the answer is its result as
JSON; `azathoth.remote.calling` reads both from the call's method on
`Azathoth`, so `call_signature(name)` says how any call travels. A value
of bytes, a run's file, travels in base64. A client writes neither the
arguments it does not give nor those it gives as their default, so a
remote's defaults are always the call's own. An `ApiError` is answered
with its own code and the status its kind is given, `API_ERROR_STATUSES`
in `azathoth.remote.service`.

An `ApiError`'s refusal names, in `kinds`, the code of its kind and of
each kind it descends from, nearest first, and a `ModelInUseError`'s
carries its `dependents` (ADR 0137):

```json
{"error": "Workflow <ID> has no revision 3.", "code": "revision_not_found", "kinds": ["revision_not_found", "not_found", "error"]}
```

`azathoth.remote.refusals` reads a `Refusal` back as the error a local
instance would have raised, of the nearest kind this Azathoth knows,
`api_error(status, refusal)`; a refusal of none is a `RemoteRefusedError`
with its status and code, or a `RemoteUnavailableError` for 503.
`azathoth.api.connect` is the client: an instance whose every call is
`POST /v1/calls/<NAME>` to the remote, read and written by the same
signatures.

Each caller is answered by an instance of their own, `CallerInstances`,
whose author is their principal's name, so what they import, create or
authorize is recorded as theirs. A call asks the policy its actions about
the resource it names, as `<KIND> <ID>`, and each condition it names,
from its arguments before it runs or from its result before that is sent
(`azathoth.remote.conditions`): a change is never made, and restricted
data never sent, to a caller the policy refuses. A listing leaves out
what the policy refuses, so it may answer empty, never refused.

The eight calls that take a callback for their events, such as `runs.run`
and `benchmarks.run`, are jobs: a remote queues each for its runners, as
its caller, and answers `202` at once with where to follow it (ADR 0138).
A remote that runs no jobs refuses them, and one serving only the
protocol serves no call:

```text
<NAME> runs as a job on a remote's runners, and this remote runs none.
This remote serves only push, pull and status, not the service API.
```

`GET /v1/service` says which Azathoth serves the remote, the service API's
stability, the protocol, and its policy's edition and detail. `GET
/v1/permissions` says, for every action, whether the policy allows the
caller it, and why not; `POST /v1/permissions` asks the same of up to 100
resources at once. Any caller the remote knows may ask either, since the
answer is only about them.

### The Audit

A remote tells its audit before it acts, and before it sends what it read
(ADR 0136): a push, with how many revisions it offers, before anything is
received; each change a call makes, naming the call, before it is made;
and a capabilities read, a pull, a content read, a portfolio read or a
restricted read before it is sent. Reading what is not restricted through
a call tells nothing. A change or a push that then fails is followed by
`request_failed`, naming why, and a refusal for want of a token or
permission is told as `request_denied`. An audit that cannot be told stops
the request, so nothing is changed and nothing sent:

```text
This remote could not tell its audit what was asked, so it did nothing; its log says why.
```

A refusal is answered whether or not the audit can be told of it.

A remote answers requests together (ADR 0135). Every call to a seam or a
repository runs off the event loop, in a thread, so a slow policy or a
long push holds up no other request; at most `max_concurrent` such calls
run at once, eight by default, as many as a PostgreSQL database's pool
holds connections. Its reads are read-only transactions, so they run side
by side and alongside a push.

Two pushes of one lineage may arrive together, both built on its latest
revision. Each lineage's first new revision is saved fast-forward only,
checked in the transaction that saves it, so the second is answered 409
as a diverged lineage, and told to pull first, rather than forking it;
one that loses the race to the identical revision finds it held. This
holds between the threads of one server and between servers on one
PostgreSQL database.

SQLite serves one remote process on one machine, so `azathoth remote
serve` holds an exclusive lock on `<DATABASE>.serve-lock`, beside an
SQLite database, while it serves (`azathoth.remote.serving`). A second
server on the same file is refused before it serves anything:

```text
Another azathoth remote serve is already serving <DATABASE>. SQLite serves one remote process on one machine. For more than one process, or a database another machine reaches, use PostgreSQL.
```

The operating system releases the lock when the server's process ends,
however it ends; the file stays. Other commands never take it, and a
PostgreSQL database takes none, so several servers may serve one.

`pull(request, ...)` gathers a pull at the remote: the closure of what it
asks for, without the revisions the client holds. A benchmark with a
restricted revision comes only to a pull with `include_restricted`;
otherwise it is named in `withheld`, and the rest still comes.

## Status

`relation(local, remote)` says how a lineage here relates to the same
lineage at a remote, from each side's chain of revision digests, oldest
first (ADR 0125):

| Relation | When |
| --- | --- |
| `in_sync` | Both sides' latest revision is the same |
| `ahead` | The remote's latest is one this instance's latest was reached by; a push moves it forward |
| `behind` | This instance's latest is one the remote's was reached by; a pull moves it forward |
| `diverged` | Neither; a push is refused, and a pull forks it here |
| `local_only` | Only this instance holds it |
| `remote_only` | Only the remote holds it |

A `RemoteStatus` holds a `ComponentStatus` for each lineage, and a
`ModelStatus` for each model, saying whether it is authorized here and at
the remote. A push warns, and never refuses, of what would stop its
documents from running at the remote, in its report's `warnings`, which
`push_warnings(client, bundle, ...)` gathers once it is pushed:

```text
Tool <TOOL_ID>@<VERSION> needs <NAME>, which is not set at the remote; its steps fail there until it is.
Step <STEP_ID> of workflow <WORKFLOW_ID> runs workflow <CHILD_ID>, which is in production at the remote as revision <RUNNING>, not <LATEST>, the latest here.
Step <STEP_ID> of workflow <WORKFLOW_ID> runs workflow <CHILD_ID>, which is not in production at the remote; it cannot run there until the child is promoted.
Step <STEP_ID> of workflow <WORKFLOW_ID> uses model <MODEL>, which the remote has not authorized; it cannot run there until the remote's portfolio holds it.
```

A tool's credentials are the environment variables its implementations
need, `credential_names(document)`: a process implementation's grants, a
grant ending in `*` covering every variable it begins, and an MCP
implementation's `authorization` variable. Only names are read. A child
is invoked, so it runs at its production revision; a child named only when
its step runs cannot be checked. A step that chooses its model by
requirements is not checked either, since the remote's portfolio decides
which model it runs on.

## Inspection

A client's status asks the remote three things, each read-only
(ADR 0125). `heads(request, ...)` answers with the `Head` of each lineage
asked about, or of every one held when none is: its latest revision's
chain of digests, oldest first, its number there, and, for a workflow, the
digest of the revision in production there. `portfolio_records(portfolio)`
names each model the portfolio authorizes and its declared data policy.
`missing_credentials(request, environ)` says which of the credential names
asked about the environment does not set, a grant ending in `*` set when
any variable it begins is; it never reads or returns a value.

A client keeps the last portfolio it read from each remote, and when, as a
`PortfolioSnapshot` in `remote_portfolio_snapshots` (schema version 6),
one per remote URL, each read replacing the last. When the remote cannot
be reached, status reads its models from the snapshot, as of its time.
`Repositories.remote_portfolio_snapshots` opens the repository a database
needs.

An instance names the remotes it reaches as `NamedRemote`s in `remotes`
(schema version 7), each a name of letters, digits, `_` and `-` for a
URL and the variable its token is read from, `AZATHOTH_REMOTE_TOKEN`
unless another is given; the token itself is never kept (ADR 0126).
`RemoteRepository` adds, gets, lists by name and removes them, refusing a
name already given or one never given as a `RemoteNameError`, and
`Repositories.remotes` opens the repository a database needs.

## The Client

`RemoteClient(url, token)` speaks the protocol over httpx, and is a
context manager. Each refusal is a `RemoteError` carrying the remote's own
message and status: a `RemoteDivergedError` for 409, a
`RemoteNotFoundError` for 404, and a `RemoteRefusedError` for any other.
A remote not reached, or one that answers as no remote does, is a
`RemoteUnreachableError`:

```text
The remote at <URL> could not be reached: <REASON>
The remote at <URL> answered <STATUS> without saying why; it may not be an Azathoth remote.
The remote at <URL> answered with something other than a <MODEL>; it may not be an Azathoth remote, or not of this protocol.
Remote URL '<URL>' is not an http or https URL.
```

`push_to(client, roots, ...)` reads the remote's capabilities, and refuses
another protocol before sending anything. It refuses restricted data a
remote does not accept before sending any, offers the closure's digests,
sends the content the remote lacks, then the revisions it lacks, and
returns a `PushReport`. `pull_from(client, roots, include_restricted=...)`
asks for the documents, naming the revisions held here, fetches the
content the bundle holds that is not here, checked against its digest,
and saves the rest with `receive(..., fork=True)`, returning a
`PullReport`. `status_of(client, roots, ...)` compares the two sides: the
heads of the lineages named, or of every one either side holds, here and
at the remote, each related, and each model authorized on either side or
fixed by a reported workflow's step. It refreshes the remote's portfolio
snapshot, and when the remote cannot be reached, it reports each relation
as None and reads the remote's models from the last snapshot. The service
API's `instance.remote(url)` and `azathoth remote push` and `pull` call
them.

## Tokens

The core's `TokenAuthenticator` reads the tokens a remote's owner issues
with `azathoth remote token create`. A token is `azr_` and 256 random bits,
shown once; the remote keeps only its `token_digest`, in `remote_tokens`
(schema version 5), so a database that leaks holds no token that works.
A request carries one as `Authorization: Bearer <TOKEN>`, and an active
token names its owner, as the token's name. A revoked token is kept, with
when it was revoked, and names no one.

`SqlRemoteTokenRepository` keeps tokens in either database, and
`SQLiteRemoteTokenRepository` in an SQLite file; `Repositories.remote_tokens`
opens the one a database needs.

`azathoth remote token create` and `revoke` tell the audit the remote
serves with, its installed plugin's or the core's, before the token
changes (ADR 0136). The event names its principal `operator:<AUTHOR>`,
whoever ran the command, since a token command is never a request; a
command whose audit cannot be told changes nothing.
