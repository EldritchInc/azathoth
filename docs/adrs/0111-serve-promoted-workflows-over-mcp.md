# ADR 0111: Serve Promoted Workflows Over MCP

- Status: Accepted; amended by ADR 0120
- Date: 2026-11-05
- Decided in: #135

## Context

The Model Context Protocol lets an AI client, such as Claude Desktop, an IDE
or an organization's own agent, call tools a server offers. A workflow that
has been optimized and promoted is exactly such a tool: a known task with a
measured answer, recorded and resumable. ADR 0097 named Azathoth-MCP as one
of the programs its job envelope was made for.

Three things in Azathoth shape how it can be offered:

- The 1.x compatibility promise covers documents, the CLI and the database
  schema, and not the Python API, which may change in a minor release. An
  MCP server written against that API has to move with it.
- A workflow declares no input or output schema. Its steps name the values
  they read, but nothing says what shape a run's input must be.
- The CLI's input policy accepts file references (ADR 0096). That is right
  for an operator at their own terminal, and wrong for a server, where it
  would let a caller read the server's files.

An MCP server is also an attack surface. A tool an agent can see is a tool
an agent can be talked into calling, so what is offered has to be chosen,
not discovered. Over HTTP the server sits on a network, and the protocol's
own authorization specification (revision 2026-07-28) says how it must
authenticate its callers.

## Decision

### A separate distribution, released in lockstep

The server is its own distribution, `azathoth-mcp`, in this repository,
under `packages/azathoth-mcp`, with its import package `azathoth_mcp`. It
has the version of `azathoth-ai`, is released with it from the same tag, and
requires `azathoth-ai == X.Y.*` for its own `X.Y`. Because the two always
move together, it may use Azathoth's Python API, including the modules the
CLI is built from, as it stands in that minor release; a test pins the
versions and the requirement together.

It depends on the official MCP Python SDK, `mcp >= 2.3, < 3`, and on PyJWT
with its cryptography extra for validating tokens. `azathoth-ai` gains no
dependency; someone who never runs the server never installs the SDK.

Its exposure document, its command line and the documented shape of its
tools are covered by the 1.x promise from the release that ships it, as
Azathoth's own documents and CLI are. Its Python API is not.

It lives under `packages/` and not in a directory named `mcp` at the root,
which would shadow the SDK's own `mcp` package whenever Python runs from the
repository. Its tests are part of the repository's suite, under
`tests/mcp`, and the development install includes it, so a missing package
fails the suite rather than skipping it.

### The exposure document

What the server offers is the operator's decision, written in a JSON
exposure document, as every other Azathoth document is JSON. It lists the
workflows to expose, and for each its workflow ID, a tool name, a
description written for the model that will read it, and an optional JSON
Schema for the workflow's input.

The document lives in a file the operator names, not in the database. It is
reviewed and versioned with the rest of a deployment's configuration, and
exposing a workflow never needs a migration. It is read and validated once,
when the server starts, and a document that is invalid in any way stops the
server with an exact message: a duplicate or malformed tool name, a tool
name the server keeps for itself, an input schema that is not valid JSON
Schema (Draft 2020-12), or a workflow with no active production state.

### Tools

Each exposed workflow is one tool. There is never a generic tool that
invokes a workflow by ID: an agent can call only what the operator listed,
under the name and description the operator wrote.

A tool's input is an object with two properties:

- `input`, the workflow's input, which must match the entry's input schema
  if it has one and may be any JSON value if it has none;
- `idempotency_key`, optional.

The server validates `input` against the schema before anything is recorded
or run. A tool declares no output schema yet. Its result carries the
invocation's ID, status and result as structured content, with the same
result as text for clients that read only text.

Promotion still decides what runs. Each call invokes the workflow's active
production state as it is at that moment, so a workflow promoted again is
served at its new revision without a restart, and one with no active state
any more is refused with a message the model can read.

The server offers one tool of its own, `get_invocation`, which returns an
invocation's result and its evidence: what `invocation show` reports, its
runs, steps and revision, and the caller metadata it was recorded with. It
answers only for invocations of exposed workflows.

A refused call, for an unknown tool, a missing scope, arguments that do not
match the tool's schema, a workflow no longer active or an invocation the
caller may not read, is a tool result marked as an error whose text says
why, never a protocol error, so the model can correct the call. Any other
failure is the server's: it is logged in full on the server, and the
client is told only that it happened, so nothing of the server's state
reaches it.

Nothing that changes what a workflow is, such as promoting, importing or
optimizing, is offered. If an organization wants an agent to manage
workflows, it can write a workflow that does it, and expose that,
deliberately.

### Invoking

A tool call is a job: the server builds an `invoke` request in the job
envelope and runs it as `job run` does (ADR 0097, ADR 0105). If the call
names an idempotency key, a repeated call replays the recorded result, a
call whose invocation was interrupted resumes it, and a call that finds it
still running is refused. If it names none, the server makes one and
returns it with the result, so a client that gave up waiting can ask again
under that key.

The server records who called in the invocation's caller metadata, under
`mcp`: the transport, the tool's name, and over HTTP the token's subject and
client ID. The database schema does not change, and `invocation show`
already prints caller metadata.

The server keeps the runtime it composed when it started, and composes a
new one only when a call finds that the workflow it invokes has another
active state than the kept runtime holds, as after it is promoted again.
Composing a runtime discovers provider models, which is too slow for every
call; the cost is that other changes, such as a model authorized or a tool
imported, reach a running server only when it restarts.

The tool call waits for the invocation to finish, and the server sends the
client a progress notification as each step completes. A client that times
out loses nothing: the invocation keeps its key, and calling again with the
key, or reading it with `get_invocation`, returns its result. The protocol's
tasks, which let a call return before its work is done, wait for a later
release.

### Inputs

Inputs are inline values only, on both transports. A tool's `input` is the
value the workflow runs on, never a reference the server resolves. File
references would let a remote caller read the server's files, and an
input's size is already bounded by the SDK, which refuses request bodies
over 4 MiB. Reading references, starting with `s3://` behind an operator's
explicit permission, can be added later.

### Two transports

The server runs over one of two transports:

- **stdio**, for a local client that starts the server itself. It reads
  the same environment as the CLI, for its database and its models'
  credentials, and needs no authorization of its own: whoever can start
  the process already has those credentials.
- **Streamable HTTP**, for a team sharing one server and one PostgreSQL
  database. It is protected as below. It is stateless: each request is
  served on its own, under its own token, and a call's progress is streamed
  back in its own response. The endpoint is `/mcp`, so the resource URL
  ends in `/mcp`.

### Authorization over HTTP

Over HTTP the server is an OAuth 2.1 resource server, as the MCP
authorization specification requires. It issues no tokens and signs no one
in; the organization's identity provider, such as Entra ID, Okta, Cognito
or Keycloak, does.

- The server publishes Protected Resource Metadata (RFC 9728), naming the
  identity provider as its authorization server and every scope its tools
  need, and answers an unauthenticated request with a 401 that points to it.
- Every request carries a bearer token, which the server validates with
  PyJWT against the provider's published keys: its signature, by an allowed
  algorithm only; its issuer; its audience, which must be this server's own
  resource URL (RFC 8707); and its expiry, which it must have. An operator
  may also cap a token's lifetime.
- Each exposed tool requires its own scope, `azathoth:invoke:<tool>`.
  `get_invocation` requires `azathoth:read`, and returns only invocations
  recorded with the caller's own subject unless the token also carries
  `azathoth:read:all`.
- The server never passes a token on to anything else, and never logs one.
- The SDK's checks of a request's `Host` and `Origin` headers are on, which
  stops a web page from reaching a local server through DNS rebinding. A
  server answers its resource URL's host, or loopback names without
  authorization, and any other host or origin the operator allows.
- The server runs without authorization only when it is bound to a loopback
  address, `127.0.0.1` or `::1`, and refuses to start unauthenticated on any
  other.

### The container image

The signed image installs both distributions, so one image runs the CLI,
the worker and the server. The server is started through tini, by naming
tini as the entrypoint and the server's command after it. The AWS stack does not yet run it; that waits until the
stack itself has run on Fargate.

## Consequences

### Positive

- Any MCP client can call a promoted workflow, and gets the invocation's
  ID back with every result, so what an agent did can be traced to its
  runs and evidence.
- What an agent can do is exactly what the operator listed, and over HTTP
  exactly what each caller's token allows, tool by tool.
- Every call is recorded with who made it, without changing the database.
- Retried calls never run twice, because every call is a keyed job.
- `azathoth-ai` is unchanged for everyone who never runs the server.

### Negative

- Two distributions must be built, published and installed together, and
  a release publishes both or neither.
- A workflow's input schema is written in the exposure document, apart from
  the workflow it describes, and can fall out of step with it.
- A long invocation holds its tool call open until it finishes, and a
  client with a short timeout has to call again with its key.
- A running server sees a newly authorized model or imported tool only
  after a restart.
- Inputs too large to send inline cannot be passed until references are
  allowed.

## Alternatives Considered

### Ship the server inside `azathoth-ai`

Rejected. Every user would install the SDK and its web stack, and the
server would be bound by nothing stronger than the Python API it uses.

### Keep the exposure list in the database

Rejected. Exposing a workflow would need a schema change under the 1.x
promise, and a change to what agents may call would happen in a database
rather than in reviewed configuration.

### One tool that invokes any workflow by ID

Rejected. An agent could call anything in the database, including what was
never meant for it, and every tool would share one description.

### Derive tool schemas from the workflows

Deferred. Workflows declare no input schema today. When they do, the
exposure document's schema can default to the workflow's own.

### Validate tokens by introspection

Deferred. Introspection asks the identity provider about every token, and
not every provider offers it. Signed tokens can be checked by the server
alone; introspection can be added for providers that issue opaque tokens.

### Return before the invocation finishes

Deferred. The protocol's tasks would free the tool call, but they are newer
than tool calls themselves and not every client supports them. A keyed call
that can be repeated gives the same safety now.
