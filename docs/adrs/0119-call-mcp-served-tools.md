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

## Consequences

- A capability served over MCP becomes a tool like any other: it is
  resolved by requirement, verified by test cases and recorded as evidence.
- An implementation names exactly what it calls, so its evidence does too.
- A credential's value never enters a document, a digest or evidence.

## Alternatives Considered

### Write a process tool that speaks MCP

Rejected. Every such tool would carry its own client, pin nothing, and hide
the server it calls inside its source, where neither evidence nor an
operator could see it.

### Keep the server, tool and pin as process fields

Rejected. A binding is not a script and its interpreter; the fields an MCP
implementation declares and those a process one declares share only the
timeout and the grants of a stdio server.
