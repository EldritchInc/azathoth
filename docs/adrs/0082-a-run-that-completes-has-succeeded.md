# ADR 0082: A Run That Completes Has Succeeded

- Status: Accepted
- Date: 2026-10-25
- Decided in: #101

## Context

ADR 0024 introduced failure policies, so a run can contain executed, failed
and skipped steps at once. The run's own status, however, still meant "failed
when any step failed".

That made every workflow built to tolerate failure report failure when its
tolerance worked: a redundant workflow whose fallback answered, after its
primary failed under `continue`, was a failed run. Exit statuses, histories
and production results all said "failed" for runs that did exactly what they
were designed to do.

## Decision

A run that completes has succeeded, even when steps whose failure policy
tolerates failure failed along the way. A run fails only when it halts: a
`fail_workflow` step failed, and the run stopped.

```text
failure under continue or skip_dependents   run completes   succeeded
failure under fail_workflow                 run halts       failed
```

`WorkflowRun.halted` records whether the run halted, and
`WorkflowRun.halting_step_id` names the first `fail_workflow` failure in
declared order, the one the run reports.

Runs recorded before this decision leave both fields unset and are judged the
old way, failed when any step failed, so recorded history keeps its meaning
(ADR 0077).

Tolerated failures remain evidence. They still count in run statistics and
reliability metrics, and benchmarks still judge a run that never produced its
result as a run failure (ADR 0073).

`workflow run` exits 0 when the run ends in a `result` record, and 1 when it
halted or did not produce its declared result (ADR 0083).

## Consequences

### Positive

- Resilient workflows report success when their resilience works.
- "Failed" means something halted.
- Old runs keep their recorded meaning.

### Negative

- A succeeded run may contain failed steps, so "succeeded" alone does not mean
  every step worked.

## Alternatives Considered

### Fail a run when any step failed

Rejected. It punishes the tolerance that failure policies exist to express.

### A third status for partial success

Rejected. The step records already describe partial failure. A run's status
only needs to say whether it halted.
