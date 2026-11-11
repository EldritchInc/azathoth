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
