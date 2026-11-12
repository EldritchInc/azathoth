# Serving Workflows Over MCP

`azathoth-mcp` offers promoted Azathoth workflows as
[Model Context Protocol](https://modelcontextprotocol.io) tools, so an AI
client, such as Claude Desktop, an IDE or your organization's own agent, can
call them (ADR 0111).

Only the workflows you list are offered, each as one tool, under the name
and description you write for it. Every call runs the workflow's active
production revision as a recorded invocation, exactly as `job run` does, and
returns the invocation's ID with its result, so whatever an agent did can be
traced to its runs and evidence.

To go the other way, and call a tool another MCP server serves from a
workflow step, see [Calling MCP Tools](mcp-tools.md).

The server runs in one of two ways:

- over **stdio**, for one local client that starts it;
- over **Streamable HTTP**, for a team, as an OAuth 2.1 resource server in
  front of your organization's identity provider.

This guide covers macOS and Windows. Each command is shown twice:

- for the macOS Terminal (zsh or bash);
- for Windows PowerShell 7.

On Linux, the macOS commands work unchanged.

## What You Need

- Azathoth installed in a venv, as in [Installing Azathoth](install.md), and
  that venv active.
- A clone of the repository, for the example workflow this guide exposes, as
  in [Getting Started](getting-started.md).
- For HTTP with authorization, an identity provider that issues signed JWT
  access tokens, such as Microsoft Entra ID, Okta, Amazon Cognito or
  Keycloak.

## 1. Install It

`azathoth-mcp` is its own package, released with Azathoth at the same
version. It requires exactly the same minor release of `azathoth-ai`, so
install it into the venv Azathoth is in:

```bash
python -m pip install azathoth-mcp
azathoth-mcp --version
```

```powershell
python -m pip install azathoth-mcp
azathoth-mcp --version
```

It prints its version, which is Azathoth's. Upgrade the two together; pip
refuses to pair one with another minor release of the other.

## 2. Promote a Workflow

The server offers only workflows that are active in production. This guide
uses the word-count example, which needs no model. From the root of your
clone:

```bash
azathoth init
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/word-count-messages.json
azathoth workflow promote a1000000-0000-4000-8000-000000000002
```

```powershell
azathoth init
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/word-count-messages.json
azathoth workflow promote a1000000-0000-4000-8000-000000000002
```

A workflow you have optimized is promoted the same way, from its experiment
(see [Promote It](getting-started.md#6-promote-it)).

## 3. Expose It

What the server offers is written in an **exposure document**, a JSON file
you keep with the rest of your deployment's configuration. Save this as
`exposure.json` in the root of your clone:

```json
{
  "version": 1,
  "tools": [
    {
      "workflow_id": "a1000000-0000-4000-8000-000000000002",
      "name": "count_words",
      "description": "Count the words in a piece of text. Takes the text as a string.",
      "input_schema": {"type": "string"}
    }
  ]
}
```

Each entry of `tools` offers one workflow:

| Field | Meaning |
| --- | --- |
| `workflow_id` | The workflow to offer. It must be active in production. |
| `name` | The tool's name: 1 to 64 letters, digits, `_`, `-` or `.`. `get_invocation` is the server's own. |
| `description` | What the tool does, written for the model that decides whether to call it. |
| `input_schema` | Optional. A JSON Schema the workflow's input must satisfy. Without one, the promoted workflow's own input schema is used, and without that, any JSON value is accepted. |
| `sensitivity` | Optional. `public`, `internal` or `restricted`: the label every call's input is given. Without one, calls are internal. See [Serving Restricted Data](#serving-restricted-data). |

A workflow is listed at most once, and a name is used once. The server reads
the document when it starts, and refuses to start if anything in it is wrong,
naming what. It also refuses while any listed workflow is not active in
production:

```text
Every exposed workflow must be active in production; these are not: "count_words" (a1000000-0000-4000-8000-000000000002). Promote each one before exposing it.
```

Promoting a listed workflow again needs no restart: each call runs the
workflow's active state as it is at that moment, and the tools are listed
with the schemas that state declares. A listed workflow that is no
longer active is refused, call by call, until it is promoted again.

## 4. Serve It Over stdio

A local client starts the server itself and talks to it over standard input
and output. To check that it starts, run it from the root of your clone:

```bash
azathoth-mcp serve --exposure exposure.json
```

```powershell
azathoth-mcp serve --exposure exposure.json
```

It waits silently for a client; standard output carries only the protocol,
and every message the server writes goes to standard error. Press Ctrl-C to
stop it. Instead of `--exposure`, you may name the document in
`AZATHOTH_MCP_EXPOSURE`. The server reads the rest of its configuration, its
database and its models' credentials, from the same environment as the
`azathoth` command.

### Claude Desktop on macOS

Add the server to `~/Library/Application Support/Claude/claude_desktop_config.json`,
with your own paths, and restart Claude Desktop:

```json
{
  "mcpServers": {
    "azathoth": {
      "command": "/Users/you/azathoth/.venv/bin/azathoth-mcp",
      "args": ["serve", "--exposure", "/Users/you/azathoth/exposure.json"],
      "env": {
        "AZATHOTH_DATABASE": "/Users/you/azathoth/azathoth.db",
        "PATH": "/Users/you/azathoth/.venv/bin:/usr/bin:/bin"
      }
    }
  }
}
```

### Claude Desktop on Windows

Add the server to `%APPDATA%\Claude\claude_desktop_config.json`, with your
own paths, and restart Claude Desktop:

```json
{
  "mcpServers": {
    "azathoth": {
      "command": "C:\\Users\\you\\azathoth\\.venv\\Scripts\\azathoth-mcp.exe",
      "args": ["serve", "--exposure", "C:\\Users\\you\\azathoth\\exposure.json"],
      "env": {
        "AZATHOTH_DATABASE": "C:\\Users\\you\\azathoth\\azathoth.db",
        "PATH": "C:\\Users\\you\\azathoth\\.venv\\Scripts;C:\\Windows\\System32"
      }
    }
  }
}
```

Name the database by its full path, since the client starts the server in a
folder of its own choosing. Put the venv first on `PATH`: process tools, such
as the example's, start `python` from the `PATH`, and it must be the venv's.
Pass your model credentials, such as `OPENROUTER_API_KEY`, under `env` too
when an exposed workflow needs them.

## 5. What a Call Returns

A client sees `count_words` and `get_invocation`. A call of `count_words`
takes the workflow's input and, optionally, an idempotency key:

```json
{"input": "the old ones wait and dream", "idempotency_key": "guide-1"}
```

It returns the job envelope's result (ADR 0097), as structured content and
as the same JSON in text:

```json
{
  "status": "succeeded",
  "replayed": false,
  "idempotency_key": "guide-1",
  "invocation_id": "e633c021-d286-4403-a237-9e9011ae5aa4",
  "result": {"result": 6},
  "error": null
}
```

- **The key makes a call safe to repeat.** The same call with the same key
  returns the recorded result, `replayed: true`, without running again. One
  whose invocation was interrupted resumes it, and one still running is
  `incomplete`. The same key with other input, or from another caller, is an
  `idempotency_conflict`. A call without a key is given one, which the
  result names, so a client that gave up waiting can ask again under it.
- **A call that does not succeed is marked as an error,** with its `status`,
  `failed`, `rejected` or `incomplete`, and the error's code and message.
  An input or a result that breaks the promoted workflow's schemas fails
  with `invalid_input` or `invalid_output`, naming every violation.
- **Every workflow tool names its `outputSchema`,** the shape above. The
  value under `result.result` is held to the promoted workflow's output
  schema, if it declares one, so a client can check what it receives.
- **A call that is refused,** for an unknown tool, arguments that do not
  match the tool's schema, or a workflow no longer active, is an error whose
  text says why, so the model can correct it:

```text
The arguments of "count_words" are not valid: $.input: 5 is not of type 'string'.
```

The server sends a progress notification as each of the workflow's steps
finishes, to a client that asks for progress. Inputs are always the value the
call sends: the server never reads a file or any other reference for them.

## 6. Read an Invocation's Evidence

`get_invocation` takes an invocation ID and returns what `invocation show`
reports, as data: the input, the outcome, who called, and the run, step by
step:

```json
{"invocation_id": "e633c021-d286-4403-a237-9e9011ae5aa4"}
```

```json
{
  "invocation_id": "e633c021-d286-4403-a237-9e9011ae5aa4",
  "workflow_id": "a1000000-0000-4000-8000-000000000002",
  "tool": "count_words",
  "created_at": "2026-11-05T16:52:51.835625Z",
  "status": "succeeded",
  "result": {"result": 6},
  "error": null,
  "idempotency_key": "guide-1",
  "input": "the old ones wait and dream",
  "caller": {"mcp": {"transport": "stdio", "tool": "count_words"}},
  "run": {
    "run_id": "f9c17604-2607-438b-9995-8274488e13b9",
    "finished": true,
    "resumes": 0,
    "workflow_revision": 1,
    "started_at": "2026-11-05T16:52:51.839179Z",
    "completed_at": "2026-11-05T16:52:51.873046Z",
    "halted": false,
    "steps": [
      {"step_id": "a1000000-0000-4000-8000-000000000021", "status": "executed", "attempts": 1, "confidence": null},
      {"step_id": "a1000000-0000-4000-8000-000000000022", "status": "executed", "attempts": 1, "confidence": null}
    ]
  }
}
```

Every invocation records its caller under `mcp` in its caller metadata, so
`azathoth invocation show` names it too. It reads only invocations of
workflows the server exposes.

## 7. Serve a Team Over HTTP

Over HTTP, many clients share one server and, usually, one PostgreSQL
database (see [Installing Azathoth](install.md)). The server is an OAuth 2.1
resource server: it issues no tokens and signs no one in. Your identity
provider does, and the server accepts a request only with a bearer token
that is a signed JWT, which:

- is signed by an allowed algorithm, RS256 or ES256 unless you name others,
  with one of the provider's published keys;
- comes from the provider's issuer;
- names the server's own URL as its audience (RFC 8707), so a token issued
  for another service is refused;
- has an expiry, and names its subject.

### Set Up the Identity Provider

Register the server with your provider as an API, or resource, whose
identifier is the URL clients connect to, ending in `/mcp`, such as
`https://mcp.example.com/mcp`. Tokens for it must carry that URL as their
audience. Then define the scopes it grants:

| Scope | Allows |
| --- | --- |
| `azathoth:invoke:<tool>` | Calling one exposed workflow's tool, such as `azathoth:invoke:count_words` |
| `azathoth:read` | `get_invocation`, for the invocations the caller made itself |
| `azathoth:read:all` | `get_invocation`, for every invocation of an exposed workflow |

A caller sees only the tools its token allows. The server reads scopes from
the token's `scope` claim, or `scp` as some providers write it.

### Start the Server

```bash
azathoth-mcp serve --exposure exposure.json --transport http --host 0.0.0.0 --port 8000 --issuer https://idp.example.com/tenant --resource https://mcp.example.com/mcp
```

```powershell
azathoth-mcp serve --exposure exposure.json --transport http --host 0.0.0.0 --port 8000 --issuer https://idp.example.com/tenant --resource https://mcp.example.com/mcp
```

`--issuer` is the provider's issuer, exactly as its tokens carry it. The
server finds the provider's keys in its OpenID Connect or OAuth metadata,
and refuses to start if it can't; name them with `--jwks-url` when the
provider publishes no metadata. Further options:

| Option | Meaning |
| --- | --- |
| `--algorithm NAME` | A signing algorithm to accept, instead of RS256 and ES256; repeat for more. Only public-key algorithms are allowed. |
| `--max-token-lifetime SECONDS` | Refuse tokens issued to live longer than this. |
| `--allowed-host HOST` | Another `Host` header to answer, such as a load balancer's health check; repeat for more. |
| `--allowed-origin ORIGIN` | A browser `Origin` to allow; repeat for more. |

The server answers only requests whose `Host` is the resource URL's host or
one you allow, so a web page cannot reach it through DNS rebinding. Put it
behind TLS: clients connect to the HTTPS resource URL.

### What Clients See

A request without a valid token is refused with `401`, and a
`WWW-Authenticate` header that points to the server's Protected Resource
Metadata (RFC 9728), at `/.well-known/oauth-protected-resource/mcp`. It names
the provider and every scope the server's tools need, so an MCP client knows
where to get a token and what to ask for.

Every invocation records the token's subject and client with its caller, so
the audit trail names who called. A caller with `azathoth:read` reads only
its own invocations; any other is not found:

```text
No invocation e633c021-d286-4403-a237-9e9011ae5aa4 was found.
```

The server never logs a token, never passes one on, and keeps none beyond
its request.

### Try HTTP Without an Identity Provider

Without `--issuer` and `--resource`, the server authorizes no one, so it
listens only on a loopback address. It is for trying a client on your own
machine:

```bash
azathoth-mcp serve --exposure exposure.json --transport http
```

```powershell
azathoth-mcp serve --exposure exposure.json --transport http
```

Clients connect to `http://127.0.0.1:8000/mcp`. On any other address it
refuses to start:

```text
Without --issuer and --resource, the server authorizes no one, so it listens only on a loopback address, such as 127.0.0.1 or ::1; got --host 0.0.0.0.
```

## 8. In the Container

The container image holds the server too (see
[Running in a Container](container.md)). Start it through tini, the image's
init process, with the exposure document's folder mounted:

```bash
IMAGE=ghcr.io/eldritchinc/azathoth:1.4.0
docker run -i --rm -v azathoth-data:/var/lib/azathoth -v "$PWD:/mcp:ro" --entrypoint /usr/bin/tini $IMAGE -- azathoth-mcp serve --exposure /mcp/exposure.json
```

```powershell
$IMAGE = "ghcr.io/eldritchinc/azathoth:1.4.0"
docker run -i --rm -v azathoth-data:/var/lib/azathoth -v "${PWD}:/mcp:ro" --entrypoint /usr/bin/tini $IMAGE -- azathoth-mcp serve --exposure /mcp/exposure.json
```

That serves over stdio; `-i` keeps standard input open. A local client can
run the same `docker run` as its command. To serve over HTTP, add
`--transport http --host 0.0.0.0` with `--issuer` and `--resource`, and
publish the port with `-p 8000:8000`. Inside a container, only an authorized
server can be reached from outside it.

## Serving Restricted Data

A client that holds restricted data, a HIPAA assistant sending patient
records to a HIPAA workflow, say, needs a tool exposed as restricted:

```json
{
  "workflow_id": "a1000000-0000-4000-8000-000000000002",
  "name": "summarize_chart",
  "description": "Summarize a patient's chart.",
  "sensitivity": "restricted"
}
```

That is your declaration that the client may send and receive restricted
data ([ADR 0123](adrs/0123-sensitivity-labels.md)). Every call's input is
labelled restricted, so its prompts reach only models declared to neither
retain nor train on data (`azathoth model policy <MODEL> --no-retention
--no-training`), and the client is given the results.

A call whose step has no such model fails, and the call's error says why:

```text
Step <STEP_ID> sent nothing. <MODEL> cannot receive restricted input: its portfolio entry does not say whether its provider retains data, and does not say whether it trains on data. If its provider neither retains nor trains on data, declare that with `azathoth model policy <MODEL> --no-retention --no-training`; otherwise choose a model that may receive restricted input.
```

A tool not exposed as restricted never returns restricted data: when
`get_invocation` names a restricted invocation of its workflow, made some
other way, it is refused:

```text
Invocation <INVOCATION_ID> is restricted, and the tool 'summarize_chart' is not exposed for restricted data, so its result is not returned. If this client may hold restricted data, the operator exposes the tool with "sensitivity": "restricted".
```

## Troubleshooting

**`Name the exposure document to serve with --exposure or AZATHOTH_MCP_EXPOSURE.`**:
`serve` was given no document. Name one.

**`No exposure document at ...`**: the path is wrong, or, for a client that
starts the server, relative to a folder other than you expected. Use a full
path.

**`Every exposed workflow must be active in production; ...`**: promote
each workflow it names (step 2), or remove it from the document.

**A tool the client should see is missing**, over HTTP: the token lacks its
scope. The server lists only what a token allows, and refuses the rest:

```text
This call needs the scope "azathoth:invoke:count_words".
```

**Every request is refused with `401`**, although the client has a token:
the token's audience is not the server's `--resource` exactly, its issuer is
not `--issuer` exactly, it has expired, or it is signed by an algorithm not
allowed. The server's log says which kind of problem it found, never the
token.

**`421 Invalid Host header`**: the request's `Host` is not the resource URL's
host. Add the name the request uses with `--allowed-host`.

**A process tool fails, or runs without Azathoth's packages**, when a
client starts the server: the server's `PATH` does not start with the venv,
so `python` is another one, or none. Set `PATH` in the client's `env`
(step 4).
