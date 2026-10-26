# ADR 0081: Record Unresolved Inputs and Unresolvable Outputs as Step Failures

- Status: Accepted
- Date: 2026-10-25
- Decided in: #101

## Context

Two failures used to escape a step's own failure policy and crash the run:

- an input with no value when its step became eligible, for example when every
  redundant producer failed under `continue`;
- an output binding whose path did not resolve against what the step returned,
  for example when a model omitted a declared key.

Both are failures of one step. Crashing the run lost its evidence, and made a
benchmark abort instead of recording a failed case.

## Decision

Both become recorded step failures, handled by the step's own failure policy.

An input that cannot resolve records the step as failed with one attempt
carrying `WorkflowInputResolutionError`. It is not retried, because resolution
is deterministic, and the step's strategy never executes:

```text
Workflow input 'x' could not resolve value 'y' from any step it depends on.
Workflow context input 'x' could not resolve event type 'e'.
```

An output binding that cannot resolve fails that attempt with
`WorkflowValueResolutionError`:

```text
Cannot resolve workflow value 'count': missing object key 'count'.
```

It is retried under the step's retry policy, because a model may produce the
declared shape on a later attempt. When attempts run out, the step fails under
its own failure policy.

A run that still produced its declared result is judged on it; otherwise
benchmarks judge it a `workflow-run-failure` (ADR 0073).

## Consequences

### Positive

- Every step failure leaves a recorded run.
- Retry policies cover malformed model output.
- Benchmarks record failed cases instead of aborting.

### Negative

- A run can now complete with steps that never executed; consumers of run
  evidence must check step status rather than assume execution.

## Alternatives Considered

### Retry unresolved inputs

Rejected. Resolution is deterministic, and a retry would fail identically.

### Crash the run

Rejected. A failure of one step would erase the evidence of all the others.
