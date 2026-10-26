# ADR 0078: Dispatch Tools by Runtime, and Run Process Tools

- Status: Accepted
- Date: 2026-10-25
- Decided in: #100

## Context

ADR 0034 executed trusted Python tools in process and anticipated other
runtimes. In-process Python covers only tools written as Python functions
against Azathoth's sandboxed builtins. Real tools are often scripts in other
languages, command-line programs, or code that must not share Azathoth's
process.

## Decision

Every tool implementation declares a runtime. `RuntimeToolExecutor`, the
executor Azathoth composes everywhere tools run (candidate generation,
production and `tool verify`), dispatches each implementation to the executor
registered for its runtime:

```text
runtime "python"   ──► PythonToolExecutor   trusted, in process
runtime "process"  ──► ProcessToolExecutor  a separate process
anything else      ──► UnsupportedToolRuntimeError
```

A `process` implementation declares the command that interprets its source,
and optionally a timeout:

```json
{"runtime": "process", "command": ["python"], "timeout_seconds": 30.0, "source": "..."}
```

`ProcessToolExecutor` writes the source to a temporary script, runs the command
with the script's path appended, sends the inputs as one JSON object on
standard input, and reads one JSON object from standard output. The source is
the script, so the implementation's digest covers exactly what executes.

A process tool that times out, or whose run is cancelled, is killed. A
non-zero exit reports its status and the tail of its standard error. Output
that is not a JSON object is a failure.

Unknown runtimes are rejected when a tool is imported and when candidates are
generated, never when a stored record is decoded, so old databases always
load:

```text
Tool implementation <ID> uses unsupported runtime 'javascript'; supported runtimes: process, python.
```

Synchronous Python entrypoints run in a worker thread, so a slow tool does not
block its concurrent siblings (ADR 0079).

## Consequences

### Positive

- Tools can be written in any language with an interpreter.
- Process tools are isolated from Azathoth's process and bounded in time.
- Verification uses exactly the dispatch production uses.

### Negative

- Process tools depend on their command existing on the machine that runs
  them.
- Process isolation is not a security sandbox.

## Alternatives Considered

### A dedicated step type for external programs

Rejected. Process tools reuse the tool contract, resolution and verification
unchanged.

### Reject unknown runtimes when decoding

Rejected. A database written by a newer version could not be opened at all.
