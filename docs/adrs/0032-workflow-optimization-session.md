# ADR 0032: Workflow Optimization Sessions

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow experiments evaluate candidate workflow populations.

Workflow optimizers produce new workflow generations from experiment evidence.

Optimization systems require a durable representation of the complete optimization process rather than isolated experiment results.

Recording optimization history enables reproducibility, benchmarking, and visualization.

## Decision

Workflow optimization is modeled as a sequence of immutable optimization generations.

Each generation records:

- the generation number;
- the experiment used as optimization input; and
- the candidate workflows produced by the optimizer.

Workflow optimization sessions expose:

- the initial candidate population; and
- the ordered history of optimization generations.

Optimization sessions contain no optimizer-specific heuristics.

Replay optimization is implemented as the canonical deterministic optimizer for validating orchestration and end-to-end optimization pipelines.

## Consequences

### Positive

- Optimization history becomes durable and reproducible.
- Entire optimization sessions can be inspected after execution.
- Optimizers remain interchangeable.
- Replay optimization provides deterministic baseline behavior.

### Negative

- Optimization sessions introduce additional immutable models.
- Long optimization runs may produce larger recorded histories.

## Alternatives Considered

### Record only the final optimized candidates

Rejected because optimization history is valuable for analysis, benchmarking, debugging, and visualization.

### Allow optimizers to mutate candidate collections in place

Rejected because immutable generations provide reproducibility and deterministic replay.