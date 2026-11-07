# ADR 0118: Workflow Input and Output Schemas

- Status: Accepted
- Date: 2026-11-07
- Decided in: #143

## Context

A workflow takes whatever JSON its caller sends and answers with whatever
its run produced. Its declared result (ADR 0071) says which value is the
answer, and promotion emits it to callers as `result` (ADR 0065), but
nothing says what shape either has. A caller learns a workflow's contract
from its author, and finds out it was broken from a failed run, or worse,
from a result it cannot use.

The one schema anywhere is the operator's, in the MCP server's exposure
document (ADR 0111): the server checks a tool's input against it, and no
other caller is checked at all. A child started by `run_workflow` is not,
nor a job, nor `workflow invoke`.

## Decision

### A workflow declares the schemas of its input and its result

A workflow specification may declare an `input_schema` and an
`output_schema`, each a JSON Schema:

```json
{
  "metadata": {"id": "<WORKFLOW_ID>", "name": "summarize a ticket", "description": "..."},
  "steps": ["..."],
  "result": {"name": "summary"},
  "input_schema": {"type": "object", "properties": {"ticket": {"type": "string"}}, "required": ["ticket"]},
  "output_schema": {"type": "string", "maxLength": 600}
}
```

The input schema describes the value the workflow receives, the payload of
its `workflow.input.received` event, after resolution: a PDF or an image is
its content handle (ADR 0112), so a schema can require a document of one
media type. The output schema describes the workflow's declared result, the
value benchmarks judge and promotion emits, so a workflow that declares an
output schema must declare a result.

Either schema is any valid JSON Schema, in the dialect its `$schema` names
or Draft 2020-12, as every schema Azathoth reads is. A schema that is not
one is refused when the workflow is built or imported, and the import says
why:

```text
The workflow's input schema is not usable: <REASON>
The workflow's output schema is not usable: <REASON>
Workflow <WORKFLOW_ID> has an output schema, which describes its result, but declares no result.
```

A specification without schemas serializes without them, so no existing
workflow's digest or revision changes.

### The schemas travel with the workflow into production

The schemas are part of the specification, so candidate generation and
materialization carry them, and promotion fixes them with the rest of the
workflow: a production state's specification holds the schemas every
invocation of that revision is checked against. `workflow show` prints a
workflow's schemas after its result, and `workflow production` prints the
promoted ones after its deployment.

### Every production invocation is checked against them

Every production invocation is checked against the schemas of the promoted
specification, so a workflow's contract is the one that was promoted. Every
path that invokes, `workflow invoke`, a job, a worker, an MCP call and a
child started by `run_workflow`, `loop_workflow` or `map_workflow`, shares
the one check. `workflow run`, benchmarks and optimization are not checked:
they are where a contract is still being written, and a schema being edited
should not break the benchmark it is being edited against.

The input is checked before any run starts. An input that breaks the input
schema fails the invocation with `invalid_input`, recorded with the
invocation, so it can be audited and its key replays it. The result is
checked once the run has produced it: a declared result, emitted as
`result`, that breaks the output schema fails the invocation with a new
code, `invalid_output`, and the run is kept and associated, so it shows what
the workflow produced. The caller receives no result. A resumed invocation's
result is checked as any other's is, and a replayed key returns the
recorded failure. Each message names every violation, by its JSON path, in
a stable order, and the failure's metadata names them as `violations`:

```text
The workflow's input does not match its input schema: <VIOLATIONS>.
The workflow's result does not match its output schema: <VIOLATIONS>.
```

```json
{"code": "invalid_input", "message": "The workflow's input does not match its input schema: $: 'ticket' is a required property.", "metadata": {"violations": [{"path": "$", "message": "'ticket' is a required property"}]}}
```

A job reports both codes as a `failed` job, not a `rejected` one, since the
invocation exists. A child whose contract is broken fails its parent's step
with its own message. A production state that emits no `result` has no
declared result to check.

## Consequences

- A workflow's contract is written once, beside its steps, and versioned
  with them.
- Every existing workflow, document and revision reads and digests as it
  did.
- Promotion fixes a contract: a workflow imported with a new schema changes
  nothing in production until it is promoted again.
- Every caller is held to the same contract, and a caller can tell a
  workflow that failed, `workflow_execution_failed`, from one that broke its
  contract, `invalid_output`.
- A child workflow's contract holds whoever starts it, so a parent finds a
  broken input where it started the child, not deep in the child's run.

## Alternatives Considered

### Keep schemas in the exposure document only

Rejected. The exposure document serves one MCP server; every other caller,
a job, a worker, a parent workflow, would go unchecked, and a contract
would be copied wherever the workflow is offered.

### Reuse `workflow_execution_failed` for a broken result

Rejected. A caller could not tell a workflow that broke from one that ran
and answered outside its contract, and only the second is the workflow's
author's to fix by changing what the workflow promises.

### Check `workflow run` too

Rejected. `workflow run` is how a workflow and its contract are developed;
a run refused for a schema still being written would hide what the
workflow actually does, which is what its author is looking at.

### Describe the production emissions instead of the result

Rejected. Promotion emits exactly the declared result, as `result`; a
schema of the emission object would describe a wrapper every promoted
workflow shares, and say nothing a benchmark could use.
