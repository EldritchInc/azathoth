# ADR 0005: Separate Optimization Orchestration from Execution

- Status: Accepted
- Date: 2026-07-30

## Decision

Introduce OptimizationRunner as an orchestration layer.

StrategyExecutor executes strategies.

Evaluators score outputs.

OptimizationRunner coordinates both.

## Rationale

Execution should not know how results are evaluated.

Evaluation should not know how strategies execute.

Optimization should consume both without coupling.

## Consequences

- easier testing
- dependency injection
- future optimizer implementations
- cleaner separation of concerns
