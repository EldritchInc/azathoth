# ADR 0026: Workflow Reliability Metrics

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow execution statistics summarize what occurred during execution.

Examples include:

- executed workflow steps;
- failed workflow steps;
- skipped workflow steps;
- retry count; and
- execution duration.

While useful for inspection, these raw statistics do not directly support comparing workflow executions.

Optimization systems require normalized metrics that remain meaningful across workflows of different sizes.

For example:

- a workflow with one retry out of two steps;
- a workflow with one retry out of one hundred steps; and
- a workflow with one skipped branch

should not necessarily be interpreted identically.

Reliability metrics provide normalized execution characteristics that can later support workflow evaluation and optimization.

## Decision

Workflow runs expose immutable reliability metrics derived directly from recorded workflow execution.

Reliability metrics include:

- completion rate;
- first-attempt success rate;
- retry rate; and
- failure rate.

Completion rate is calculated across all workflow steps.

Attempt-based metrics are calculated only across attempted workflow steps.

Skipped workflow steps are excluded from attempt-based reliability metrics because they do not represent execution outcomes.

Reliability metrics are computed on demand and are never persisted independently.

## Consequences

### Positive

- Reliability metrics are independent of workflow size.
- Reliability remains deterministic.
- No duplicated execution state is introduced.
- Future optimization systems receive normalized execution metrics.

### Negative

- Reliability metrics require computation when requested.
- Metric definitions become part of the public API.

## Alternatives Considered

### Use raw execution statistics only

Rejected because raw counts are difficult to compare across workflows of different sizes.

### Persist reliability metrics

Rejected because reliability metrics are completely derivable from recorded workflow execution.

Persisting derived values would introduce duplicated state and potential inconsistencies.