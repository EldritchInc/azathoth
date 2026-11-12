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

## The Server

`azathoth.remote.server` serves the protocol over HTTP with Starlette,
the `remote` extra, so nothing else in Azathoth imports it.
`RemoteServer(...).app()` is the application `azathoth remote serve` runs
with uvicorn:

| Route | Action | Answers |
| --- | --- | --- |
| `GET /health` | | `{"status": "ok"}`, with no token |
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
content route for its digest. A refusal is JSON, `{"error": "<MESSAGE>"}`:

| Status | Refusal |
| --- | --- |
| 400 | A malformed request, another protocol, or a path naming no digest |
| 401 | No token the remote knows |
| 403 | The policy refuses it, or restricted data the remote does not accept |
| 404 | Content the remote does not hold |
| 409 | A push whose lineage has diverged |
| 413 | A body larger than the remote accepts |
| 422 | A push or content the receiving checks refuse |

```text
This remote does not know the token given. Send one its owner created with `azathoth remote token create`, as `Authorization: Bearer <TOKEN>`.
```

Each request is audited as it is answered: a capabilities read, a push, a
pull, a content read or a portfolio read once it is served, and a refusal for want of a
token or permission as `request_denied`. Repositories are read and
written off the event loop, one request at a time, since a PostgreSQL
database's repositories share one connection.

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
documents from running at the remote:

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
`PullReport`. The service API's `instance.remote(url)` and `azathoth remote
push` and `pull` call them.

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
