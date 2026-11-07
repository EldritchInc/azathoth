# ADR 0119: Call MCP-Served Tools

- Status: Accepted
- Date: 2026-11-07
- Decided in: #144

## Context

A tool's implementation is code Azathoth runs: a Python function (ADR 0034)
or a script a process interprets (ADR 0078). A capability someone else
already serves over the Model Context Protocol, a search index, a ticket
system, a vendor's API, can only be reached by writing a process tool that
speaks MCP itself, and that tool's author pins nothing: when the server
changes the tool, the step sends arguments the tool no longer accepts, or
reads a result it no longer returns.

Azathoth already serves its workflows over MCP (ADR 0111). Calling MCP
tools is the other direction: a step of a workflow calling one tool on a
server, as it calls any other tool.

## Decision

### An implementation binds one tool a server serves

A tool implementation of the `mcp` runtime runs no source. It declares the
binding of the remote tool it calls:

```json
{
  "id": "<IMPLEMENTATION_ID>",
  "tool_id": "<TOOL_ID>",
  "tool_version": "1.0.0",
  "version": "1.0.0",
  "runtime": "mcp",
  "timeout_seconds": 20,
  "mcp": {
    "server": {"url": "https://mcp.example.com/mcp"},
    "tool": "search",
    "schema_digest": "<SCHEMA_DIGEST>",
    "credentials": {"authorization": "SEARCH_TOKEN"}
  }
}
```

The server is named by exactly one of a `command`, which starts a server
speaking over stdio, or the `url` of a server reached over streamable HTTP.
The `tool` is the name the server lists it under. The `schema_digest` pins
the tool's schemas as they were when the implementation was written: the
sha256 of the canonical JSON of the tool's `inputSchema` and `outputSchema`,
with sorted keys and no insignificant whitespace, an absent output schema
digested as null.

Credentials are named, never held. An HTTP server's `authorization` names
the environment variable whose value is sent as a bearer token. A stdio
server is a process, so it is given its credentials as any process tool is,
through the implementation's environment grants (ADR 0099); an HTTP
implementation grants none, and a stdio one names no authorization
variable.

An MCP implementation may declare a timeout. It declares no source, no
entrypoint, no command and no content inputs, and every other runtime
declares a source and no binding. The binding is part of the
implementation, so the implementation's digest, which every tool step
records, covers the server, the tool and the pin. A step binds an
MCP tool's inputs as it binds any tool's: workflow values, context values
and constants (ADR 0094).

Every implementation of another runtime reads, serializes and digests as it
did.

### A call is made only while the tool matches its pin

The `mcp` runtime has its own executor. Each call opens its own connection:
a stdio server is started for the call and stopped after it, and an HTTP
server is reached over streamable HTTP. Nothing is pooled, so concurrent
steps, a `map_workflow` among them, never share a session. The executor
lists the server's tools, reading every page, and computes the digest of
the bound tool's schemas as the server serves them now. The tool is called
only when that digest is the pinned one; a tool the server does not serve,
or serves under other schemas, is not called at all:

```text
MCP server <SERVER> serves no tool named <TOOL>.
MCP tool <TOOL> on <SERVER> no longer matches its pinned schemas: pinned <PINNED>, served <SERVED>.
```

The step's inputs are the call's arguments, exactly. The call's output is
the tool's structured content, or, when it returns none, its text blocks
joined by newlines as `text`. A result holding an image, audio or a
resource fails the step, naming the kind, until a tool's output can hold
content. A result marked as an error, a server that cannot be reached and
a call that outlasts the implementation's timeout, which covers connecting,
listing and calling together, each fail the step with a `ToolExecutionError`
that quotes at most the last 500 characters of what the server said:

```text
MCP tool <TOOL> on <SERVER> failed: <REASON>
```

A stdio server is started with the environment a process tool would be
given, the platform's base variables and the implementation's grants
(ADR 0099), and the step's trace context as `TRACEPARENT` and `TRACESTATE`
(ADR 0100). It is not Azathoth, so it is given no lineage and no timeout
variable. An HTTP server is sent the step's trace context as `traceparent`
and `tracestate`, and `Authorization: Bearer` followed by the value of the
binding's authorization variable, read when the call is made. A variable
that is not set fails the step before anything is sent, naming the
variable, never a value:

```text
MCP tool <TOOL> on <SERVER> needs its authorization variable <VARIABLE>, which is not set.
```

The SDK is the `mcp` extra, `azathoth-ai[mcp]`, imported only when an MCP
implementation runs. Where it is not installed, the step fails saying so:

```text
MCP tools need the mcp package, which is not installed; install azathoth-ai[mcp].
```

### A binding is written from what the server lists

`azathoth tool from-mcp` writes the tool document of one tool a server
serves. It is named the tool and the server, by `--url` or by a command
after `--`, and the credentials, grants and timeout its implementation
should keep. It lists the server's tools, and prints a document whose
definition takes the tool's name, description and schemas, and whose one
implementation is pinned to the digest of those schemas as they are served
now. A tool that names no output schema is given the schema of its text,
an object holding one string, `text`. Listing is given the timeout named,
or 30 seconds.

The command stores nothing. Tools are never edited in place: the operator
reads the document and imports it with `tool import`, as any tool document
is imported, and `tool verify` runs whatever test cases they add. The
document's identifiers are derived from the server and the tool, and the
implementation's from its pin too, so writing the document again names the
same tool, and a tool whose schemas changed is a new implementation of it,
imported as the tool's next revision.

## Consequences

- A capability served over MCP becomes a tool like any other: it is
  resolved by requirement, verified by test cases and recorded as evidence.
- An implementation names exactly what it calls, so its evidence does too.
- A credential's value never enters a document, a digest or evidence.
- A server that changes a tool stops every step bound to it, with a message
  naming both digests, until the implementation is pinned again; a step
  never sends arguments a tool no longer accepts.
- Every call starts a stdio server or opens an HTTP session anew, which
  costs time a pooled session would not.

## Alternatives Considered

### Write a process tool that speaks MCP

Rejected. Every such tool would carry its own client, pin nothing, and hide
the server it calls inside its source, where neither evidence nor an
operator could see it.

### Call whatever the server serves now

Rejected. A tool that changed its schemas would be sent arguments it no
longer accepts, or answer with a result its definition does not describe,
and nothing would say why the step that worked yesterday fails today.

### Keep one session per server for the life of a run

Deferred. A pooled session would save each call its connection, but a
session shared by concurrent steps is state no step owns, and nothing yet
needs the time it would save.

### Keep the server, tool and pin as process fields

Rejected. A binding is not a script and its interpreter; the fields an MCP
implementation declares and those a process one declares share only the
timeout and the grants of a stdio server.
