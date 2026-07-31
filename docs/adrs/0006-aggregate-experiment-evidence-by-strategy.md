# ADR 0006: Aggregate experiment evidence by strategy

## Status

Accepted

## Context

A single optimization run describes how one strategy performed against one
example.

Azathoth must compare candidate strategies across collections of examples.
Comparing isolated runs would require callers to repeatedly reconstruct
aggregate metrics and could allow summaries to diverge from their underlying
evidence.

## Decision

Introduce `StrategyScorecard` as the aggregate result for one exact strategy
version across multiple optimization runs.

A scorecard contains the underlying runs and derives:

- run count;
- passed count;
- pass rate;
- mean evaluation score.

Summary metrics are computed from the recorded runs rather than supplied by
callers.

Every run must match the scorecard's strategy identity, name, and version.

## Consequences

Benefits:

- experiment evidence remains the source of truth;
- aggregate metrics cannot become stale independently;
- exact strategy versions can be compared reproducibly;
- scorecards remain serializable and auditable;
- future optimizers can consume a stable aggregate model.

Costs:

- scorecards require at least one completed run;
- large experiments may create substantial nested records;
- additional metrics will require explicit model evolution.