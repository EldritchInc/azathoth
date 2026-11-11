# ADR 0124: Remote Push and Pull

- Status: Accepted
- Date: 2026-11-11

## Context

Until 1.4 every Azathoth instance kept its workflows, tools and benchmarks
to itself. A team that built a workflow on a laptop copied its JSON to the
machine that ran it, by hand, and lost the lineage ADR 0122 records: who
made each revision, what it was built on, and the digest that says two
copies are the same.

1.4 gives an instance a remote: another instance, served over HTTP, that it
pushes documents to and pulls them back from. The remote is the core's own
seam for what the team tier will build on, so it must say who may do what
without the core deciding policy, and it must not move restricted data
anywhere ADR 0123 does not allow.

## Decision

### What travels

A push sends workflows, tool versions and benchmarks: their durable
documents, and nothing an instance keeps of its own. Production state, the
model portfolio and runs never travel; a pulled workflow is promoted, and
its models authorized, by the instance that pulls it.

Each document travels as its latest revision with the revisions it was
reached by, oldest first, and with what it needs at the remote:

| A document | Needs |
| --- | --- |
| A workflow | The tool versions its tool steps match here, and the child workflows its `run_workflow` step's `call`, or its `map_workflow` or `loop_workflow` step's `settings`, names as a constant |
| A benchmark | The content its cases hold |

Dependencies come before the documents that need them, and each lineage
once. What cannot be gathered is named, one sentence each, and the rest
still goes:

```text
Step <STEP_ID> of workflow <WORKFLOW_ID> names its child workflow only when it runs, so no child is pushed with it.
```

### Digests are the identity

A revision travels as its document's JSON beside its revision digest,
parent digest and content digest (ADR 0122). The receiver checks each one
before anything reads it: the document names its lineage, its JSON digest
is the content digest, and the revision digest is the digest of the
lineage, content and parent. It then reads the document with its own
models, and refuses one it reads as other content, naming its version, so
two versions of Azathoth never store one revision under two digests:

```text
Azathoth <VERSION> reads revision <DIGEST> of workflow <WORKFLOW_ID> as content <READ>, not <CONTENT_DIGEST>; send it from an Azathoth that reads it as its digest names.
```

Each instance numbers the revisions it saves; the same revision may be 3
here and 5 there, and its digest is the same everywhere. A revision already
held is skipped, so sending a bundle twice changes nothing.

### A remote moves only forward

Before pushing, a client offers its digests, and the remote answers with
those it lacks; the client sends that content, then those revisions. A
lineage's first new revision must build on the remote's latest. Otherwise
the push is refused whole, before anything of it is saved:

```text
Workflow <WORKFLOW_ID> has diverged: its latest revision here, <LATEST>, is not the one revision <DIGEST> builds on. Pull first, then push again.
```

A pull saves a diverged lineage's revisions on the revision they build on,
forking it here with `based_on` (ADR 0122), so nothing either side made is
lost, and names each lineage it forked. Which fork to keep is the
operator's call: the pulled one is the latest, and the other stays an
earlier revision, which the service API's `based_on` can build on.

### Restricted data

A remote is not declared to hold restricted data unless its operator starts
it so, with `azathoth remote serve --accept-restricted`. A push holding any,
a benchmark with a restricted case or content such a case holds, is refused
by the client before anything is sent, and by the remote if it is sent
anyway (ADR 0123):

```text
This push carries restricted data, and this remote does not accept restricted data. Its operator accepts it by starting the remote with `azathoth remote serve --accept-restricted`.
```

A pull withholds a benchmark any revision of which is restricted, and names
it, unless it asks with `include_restricted`. Content carries no label of
its own, so a pushed blob is labelled as the most sensitive case that holds
it.

### The protocol

A remote and its client speak remote protocol 1. A client reads the
remote's capabilities first, with no data sent: the protocol, its Azathoth
and schema versions, its edition, its plugins, and whether it accepts
restricted data. Either side refuses another protocol, naming both:

```text
The remote speaks remote protocol <PROTOCOL>, and this Azathoth speaks remote protocol 1; run versions of Azathoth that speak the same protocol on both.
```

| Route | Action |
| --- | --- |
| `GET /health` | None; answers anyone |
| `GET /v1/capabilities` | Read capabilities |
| `POST /v1/missing` | Push |
| `PUT /v1/content/{digest}` | Push |
| `GET /v1/content/{digest}` | Read content |
| `POST /v1/push` | Push |
| `POST /v1/pull` | Pull |

A refusal is `{"error": "<MESSAGE>"}` with a status that says its kind: 400
malformed, 401 no known token, 403 refused, 404 not held, 409 diverged, 413
too large, 422 refused by the checks. A push bundle is at most 64 MB and a
content blob at most 10 MB.

### Tokens, seams and plugins

A remote's owner issues bearer tokens with `azathoth remote token create`,
shown once. The remote keeps only each token's sha256 digest, in
`remote_tokens`, so schema version 5 adds that table. A revoked token is
kept, with when it was revoked, and names no one. A client reads its token
from `AZATHOTH_REMOTE_TOKEN`, never from a command line.

Every request but `/health` asks three seams: an authenticator who its
caller is, a policy whether that caller may do the route's action, and an
audit what was done. A push asks the policy again for each lineage it
carries, a pull for each it asks for, and a content route for its digest,
so a policy may decide by resource. The core fills each seam: its tokens
authenticate, only the owner may do anything, and nothing is audited. A
plugin replaces one by an entry point in the `azathoth.remote` group named
`auth`, `policy` or `audit`, and the policy names the edition the remote's
capabilities report. A remote with two plugins for one seam, or one it
cannot use, does not start:

```text
Two plugins fill the remote's <SEAM> seam, <FIRST> and <SECOND>; uninstall one of them.
```

The audit is told seven kinds of event: a push, a pull, a content read, a
token created, a token revoked, a request denied and a capabilities read.

### Serving, and reaching a remote

`azathoth remote serve` serves the protocol with Starlette and uvicorn, the
`remote` extra, on `127.0.0.1:8470` unless told otherwise. It speaks plain
HTTP: across machines it is reached only through TLS, at a load balancer or
proxy. The container image includes the extra, so the same image serves a
remote, as `azathoth remote serve --host 0.0.0.0`, on Fargate behind a load
balancer that ends TLS and checks `/health`.

The service API's `instance.remote(url)` returns a `Remote` with
`capabilities()`, `push` and `pull`, raising `RemoteUnreachableError`,
`RemoteProtocolError`, `RemoteRefusedError` and `RemoteDivergedError`; the
command line's `azathoth remote push` and `pull` call it. Since the
portfolio never travels, `models.matching(requirements, scope="catalog")`
names every model the providers serve that meets a pulled step's
requirements, authorized here or not.

## Consequences

- A team moves workflows, tools and benchmarks between instances with their
  lineage, and two copies of a revision are known to be the same.
- A remote never loses a revision to a push, and a pull never loses a local
  one: divergence is refused or forked, never overwritten.
- A pulled workflow is not runnable until its instance promotes it and
  authorizes its models; the catalog-scope match says which models could
  serve it.
- A PostgreSQL database must be initialized again for schema version 5, as
  for any new schema version.
- The core's remote lets only its owner in. Teams with more than one person
  need a policy plugin, which the team tier provides.
- A remote's server is one process answering one request at a time, since a
  PostgreSQL database's repositories share one connection; that is enough
  for a team's pushes and pulls, not for serving runs.

## Deferred

- Pushing and pulling evidence: executions, experiments and runs.
- Streaming runs from a remote, and redacting restricted output.
- Merging diverged lineages; 1.4 forks, and the operator chooses.

## Alternatives Considered

### Syncing the database

Copying a database, or replicating its tables, would carry production state
and the portfolio, which belong to each instance, and could not refuse
restricted data or a diverged lineage. Documents and their lineage are what
instances share.

### Keeping revision numbers

Numbers are assigned in order of saving, so two instances that each add a
revision would both call it next. Digests already name revisions everywhere
(ADR 0122); numbers stay local.

### Overwriting on push

A push that replaced the remote's latest revision would lose what another
author pushed since. Refusing, and forking on pull, keeps both until a
person chooses.

### Content inside the bundle

Inlining content would make one push as large as all of its benchmarks'
documents, sent again each time. Offered digests send each blob once, and
only when the remote lacks it.

### Identity providers in the core

OAuth or OIDC in the core would decide for every team how people sign in.
Tokens keep the core's remote usable alone, and the auth seam lets a plugin
put any identity provider in front of it.

### Tokens on the command line

A token given as an argument stays in shell history and process listings.
`AZATHOTH_REMOTE_TOKEN` keeps it out of both, as ADR 0119 keeps an MCP
server's credentials named, never written in a document.
