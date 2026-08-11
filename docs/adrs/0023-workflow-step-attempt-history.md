# ADR 0023: Workflow Step Attempt History

- Status: Accepted
- Date: 2026-08-11

## Context

Workflow retry policies allow workflow steps to recover from transient failures.

Prior to this change, successful retries discarded information about previous failed attempts.

As a result, durable workflow execution records could not answer questions such as:

- How many attempts were required?
- Which attempts failed?
- What exception occurred?
- Did retries improve reliability?

Execution history should be preserved independently from retry behavior.

## Decision

Workflow execution now records every execution attempt.

Each workflow step produces a sequence of immutable `WorkflowStepAttempt` records.

Each attempt records:

- attempt number;
- start time;
- completion time;
- either a successful execution result or a recorded failure.

Exactly one outcome must be present.

```text
WorkflowStepRun
        │
        ├── execution
        └── attempts
                ├── Attempt 1
                ├── Attempt 2
                └── Attempt N
```

Successful executions remain represented by `ExecutionResult`.

Failures are represented by `WorkflowStepFailure`, which records:

- exception type; and
- exception message.

Exception objects themselves are intentionally not persisted.

Workflow execution attempts become part of the durable `WorkflowRun` model.

## Consequences

### Positive

- Complete retry history is preserved.
- Successful execution remains easy to access.
- Failure history becomes durable.
- Workflow execution becomes auditable.
- Retry policies and execution history remain independent concerns.
- Future optimization algorithms can reason about execution reliability.

### Negative

- Workflow run objects become larger.
- Additional execution metadata is persisted.

## Alternatives Considered

### Persist only the final execution

Rejected because retry history is valuable operational information.

### Persist Python exception objects

Rejected because exceptions are runtime objects and are not suitable for durable serialization.

### Store attempts inside `ExecutionResult`

Rejected because an execution result represents one successful execution.

Attempt history belongs to workflow orchestration rather than strategy execution.