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

## Consequences

- A workflow's contract is written once, beside its steps, and versioned
  with them.
- Every existing workflow, document and revision reads and digests as it
  did.
- Promotion fixes a contract: a workflow imported with a new schema changes
  nothing in production until it is promoted again.

## Alternatives Considered

### Keep schemas in the exposure document only

Rejected. The exposure document serves one MCP server; every other caller,
a job, a worker, a parent workflow, would go unchecked, and a contract
would be copied wherever the workflow is offered.

### Describe the production emissions instead of the result

Rejected. Promotion emits exactly the declared result, as `result`; a
schema of the emission object would describe a wrapper every promoted
workflow shares, and say nothing a benchmark could use.
