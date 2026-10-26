# ADR 0069: Persist Optimization Evidence for Inspection

- Status: Accepted
- Date: 2026-10-09
- Decided in: #92

## Context

ADR 0046 persisted workflow experiment provenance. The CLI's
`workflow optimize`, however, printed a session summary and left no navigable
trail from that summary back to the runs and judgments behind it.

An optimization result that cannot be inspected cannot be trusted, or
corrected when it is wrong.

## Decision

Every generation of `workflow optimize` leaves durable, linked evidence:

```text
each candidate execution
    WorkflowRun               persisted, succeeded or failed
    WorkflowRunEvaluation     persisted, including run-failure evaluations

each generation
    WorkflowExperimentRecord  persisted
```

An experiment record holds one observation per candidate, each with its own
identity, the candidate signature, its scorecard and its runs, plus the
ranking by observation identity.

The record shares the identity of the in-memory experiment result, so the
session output names it directly, and the chain is navigable from the CLI:

```text
workflow optimize ──► Experiment ID ──► experiment show ──► run show / run feedback
```

`workflow experiments` lists a workflow's experiments, newest first.
Experiments of a workflow since removed from configuration remain listable.

## Consequences

### Positive

- Every optimization decision can be traced to the runs that produced it.
- A wrong winner can be investigated and its runs given feedback.

### Negative

- Optimization writes many records: one run and one evaluation per candidate
  execution.

## Alternatives Considered

### Persist only the winning candidate

Rejected. Losing evidence is what explains why the winner won.

### Persist summaries without run links

Rejected. A summary that cannot be followed to its runs cannot be audited.
