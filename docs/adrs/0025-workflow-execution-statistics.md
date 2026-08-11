# ADR 0025: Workflow Execution Statistics

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow execution records contain complete information about execution.

This includes:

- executed workflow steps;
- failed workflow steps;
- skipped workflow steps;
- execution attempts;
- retry history; and
- execution timestamps.

Consumers frequently need summary information such as:

- Did the workflow succeed?
- How many retries occurred?
- How many workflow steps failed?
- How many execution attempts were made?
- How long did execution take?

Requiring every consumer to compute these metrics independently duplicates logic and increases the risk of inconsistent reporting.

## Decision

Workflow execution statistics are computed directly from recorded workflow execution.

Statistics are represented by an immutable `WorkflowRunStatistics` model.

The statistics include:

- total workflow steps;
- executed workflow steps;
- failed workflow steps;
- skipped workflow steps;
- total execution attempts;
- successful execution attempts;
- failed execution attempts;
- retry count; and
- workflow duration.

`WorkflowRun` exposes computed convenience properties that delegate to the statistics model.

Examples include:

- `succeeded`
- `failed`
- `retry_count`
- `duration_seconds`

Statistics are derived from durable workflow execution records and are not persisted independently.

## Consequences

### Positive

- Statistics always remain consistent with recorded workflow execution.
- No duplicated execution state is stored.
- Common execution metrics become available through a simple API.
- Future analytics can build on a single deterministic statistics model.

### Negative

- Statistics are recomputed when requested.
- Additional derived models increase the public API surface.

## Alternatives Considered

### Persist execution statistics

Rejected because statistics are entirely derivable from recorded workflow execution.

Persisting both execution records and derived statistics introduces duplicated state that can become inconsistent.

### Require consumers to compute statistics

Rejected because identical aggregation logic would be duplicated across consumers.

Providing a canonical implementation improves consistency and simplifies workflow analysis.