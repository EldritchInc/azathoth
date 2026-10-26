# ADR 0065: Invoke Production Through Durable Invocations and Declared Emissions

- Status: Accepted
- Date: 2026-09-03
- Decided in: #73, #75

## Context

External callers need to run production behavior and get an answer back.
Operators need to know afterwards who called, with what input, what ran, and
what the caller received.

A workflow run alone answers "what ran". It does not record the external call,
and its internal evidence (every step, attempt and value) is far richer than
what a caller should see.

## Decision

`ProductionInvocation` records one external call against a workflow identity,
with the caller's input. It is independent of any production revision.

`invoke_production_workflow` executes the invocation against the workflow's
active `WorkflowProductionState`:

```text
ProductionInvocation + WorkflowProductionState
        │
        ▼
generate_production_workflow_candidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

`ProductionInvocationRun` associates the invocation with the run that served
it, so caller identity and execution evidence stay separate records.

What the caller receives is declared, not derived. `WorkflowProductionEmission`
names the caller-visible values, and `emit_production_result` projects a
completed run into them. Promotion records one emission, `result`, bound to the
workflow's declared result, so a successful invocation returns:

```json
{"result": <declared result value>}
```

A failed invocation returns a `ProductionInvocationFailure` with a stable
`ProductionInvocationErrorCode`, such as `workflow_not_deployed`,
`model_unavailable` or `workflow_execution_failed`. Failure messages are
deliberately generic. The full run is persisted, so operators follow
`invocation show` to `run show` for the cause.

An undeployed workflow fails explicitly with `workflow_not_deployed`. It never
silently runs the configured workflow instead.

The CLI exposes this as `workflow invoke <WORKFLOW_ID> --input <JSON>`, and
history as `workflow invocations` and `invocation show`.

## Consequences

### Positive

- Every production call is durable and traceable to its run.
- Callers see only what production declares.
- Internal failure detail stays out of caller-visible results.

### Negative

- Diagnosing a failed invocation takes a second step through its run.
- Callers find the answer under a `result` key rather than as a bare value.

## Alternatives Considered

### Return the whole workflow run to callers

Rejected. Internal evidence would become a public contract.

### Fall back to configured execution for undeployed workflows

Rejected. Production would run behavior nobody promoted.
