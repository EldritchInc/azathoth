# Calling MCP Tools

A workflow step can call a tool that another
[Model Context Protocol](https://modelcontextprotocol.io) server serves, such
as a search index, a ticket system or a vendor's API, as it calls any other
tool (ADR 0119). The tool is pinned: its implementation names the server, the
tool and a digest of the tool's schemas, and a step calls the tool only while
the server still serves it under those schemas.

This is the other direction from [Serving Workflows Over MCP](mcp.md), which
offers your workflows to AI clients.

This guide covers macOS and Windows. Each command is shown twice:

- for the macOS Terminal (zsh or bash);
- for Windows PowerShell 7.

On Linux, the macOS commands work unchanged.

## What You Need

- Azathoth installed in a venv, as in [Installing Azathoth](install.md), and
  that venv active, with a database initialized.
- A clone of the repository, for the example server and workflow this guide
  uses, as in [Getting Started](getting-started.md). Run every command from
  its root.

## 1. Install the MCP Extra

Azathoth reaches MCP servers with the MCP SDK, an optional extra. Install it
into the venv Azathoth is in:

```bash
python -m pip install "azathoth-ai[mcp]"
```

```powershell
python -m pip install "azathoth-ai[mcp]"
```

`azathoth-mcp`, which serves your workflows, installs it too. Without it, a
step that calls an MCP tool fails and says so:

```text
MCP tools need the mcp package, which is not installed; install azathoth-ai[mcp].
```

## 2. Write the Tool's Document

The example server, `examples/mcp/word_count_server.py`, serves one tool,
`count_words`, over stdio. `tool from-mcp` starts it, lists its tools, and
prints the tool's document. Name the tool, and give the command that starts
the server after `--`:

```bash
azathoth tool from-mcp --tool count_words -- python examples/mcp/word_count_server.py > count-words-mcp.json
```

```powershell
azathoth tool from-mcp --tool count_words -- python examples/mcp/word_count_server.py > count-words-mcp.json
```

The document's definition takes the tool's name, description and schemas as
the server lists them. Its one implementation calls the tool, pinned to the
digest of those schemas:

```json
{
  "id": "5bd45b4c-0692-5e4e-8f58-abab2d62a626",
  "tool_id": "8be0a1c2-c56c-5cc4-be7f-04799e2ff48d",
  "tool_version": "1.0.0",
  "version": "1.0.0",
  "runtime": "mcp",
  "mcp": {
    "server": {
      "command": [
        "python",
        "examples/mcp/word_count_server.py"
      ]
    },
    "tool": "count_words",
    "schema_digest": "ab44b8dc15fe419b36f3fb80cbaac3cc3f103a0229a663dc609ab81fe3cf40a3"
  }
}
```

Nothing is stored yet. Read the document, change what you need, such as the
tool's description, and add test cases if you want `tool verify` to check it.
The identifiers are derived from the server and the tool, so writing the
document again for the same tool names the same tool.

A tool that names no output schema returns its text, and its document says
so: its output is an object holding one string, `text`.

## 3. Import It and Call It From a Step

Import the document as you would any tool document:

```bash
azathoth tool import count-words-mcp.json
```

```powershell
azathoth tool import count-words-mcp.json
```

```text
Imported tool 8be0a1c2-c56c-5cc4-be7f-04799e2ff48d@1.0.0 revision 1.
```

A step asks for the tool by name, version and the `mcp` runtime, and binds
its inputs as any tool step does: workflow values, context values and
constants. `examples/mcp/count-words-over-mcp.json` passes the workflow's
input as `text`:

```json
{
  "requirement": {
    "name": "count_words",
    "version": "1.0.0",
    "runtime": "mcp"
  }
}
```

Import it and run it:

```bash
azathoth workflow import examples/mcp/count-words-over-mcp.json
azathoth workflow run a1000000-0000-4000-8000-0000000000b0 --input '"the old ones wait and dream"' --output result
```

```powershell
azathoth workflow import examples/mcp/count-words-over-mcp.json
azathoth workflow run a1000000-0000-4000-8000-0000000000b0 --input '"the old ones wait and dream"' --output result
```

It prints `6`. Each call starts the server, lists its tools, checks the
pin, calls the tool and stops the server. The step's output is the tool's
structured content, here `{"count": 6}`, or, for a tool that returns only
text, that text as `text`. Its evidence names the implementation, so a run
records exactly which server and tool it called.

## 4. When a Server Changes Its Tool

A server that serves the tool under other schemas stops every step bound to
it, rather than sending arguments the tool no longer accepts:

```text
MCP tool <TOOL> on <SERVER> no longer matches its pinned schemas: pinned <PINNED>, served <SERVED>.
```

Write the document again, read what changed, and import it. The new
schemas make a new implementation of the same tool, imported as its next
revision, so the workflow calls it without changing:

```bash
azathoth tool from-mcp --tool count_words -- python examples/mcp/word_count_server.py > count-words-mcp.json
azathoth tool import count-words-mcp.json
```

```powershell
azathoth tool from-mcp --tool count_words -- python examples/mcp/word_count_server.py > count-words-mcp.json
azathoth tool import count-words-mcp.json
```

## 5. Credentials

A server started over stdio is given only the variables a process tool is
given: the platform's base set, such as `PATH` and `HOME`, and those its
implementation grants. Grant each variable it needs with `--grant`, by name
or as a prefix ending in `*`:

```bash
azathoth tool from-mcp --tool search --grant SEARCH_API_KEY -- npx -y @acme/search-server > search.json
```

```powershell
azathoth tool from-mcp --tool search --grant SEARCH_API_KEY -- npx -y @acme/search-server > search.json
```

A server reached over HTTP is named by its URL, and sent the bearer token
the variable named by `--authorization` holds. The variable is read when
each call is made, and its value is never written to a document, a
message or evidence:

```bash
export SEARCH_TOKEN=your-token
azathoth tool from-mcp --tool search --url https://mcp.example.com/mcp --authorization SEARCH_TOKEN > search.json
```

```powershell
$env:SEARCH_TOKEN = "your-token"
azathoth tool from-mcp --tool search --url https://mcp.example.com/mcp --authorization SEARCH_TOKEN > search.json
```

Give `--timeout-seconds` to bound each call: connecting, listing and calling
together. The implementation keeps it, and `tool from-mcp` lists the tools
within it, or within 30 seconds when none is given.

## Troubleshooting

**`MCP server <SERVER> serves no tool named <TOOL>.`**: the name is not one
the server lists. Tool names are case-sensitive.

**`MCP tool <TOOL> on <SERVER> needs its authorization variable <VARIABLE>,
which is not set.`**: set the variable in the environment Azathoth runs in,
in each new terminal or in the worker's task definition.

**`MCP tool <TOOL> on <SERVER> failed: <REASON>`**: the server ran the tool
and it failed; the reason is the server's.

**A stdio server cannot be started, or cannot find its own packages**: it
runs with only the base variables and its grants, so a command found
through anything but `PATH` is not found, and a server that reads its
configuration from a variable must be granted it.
