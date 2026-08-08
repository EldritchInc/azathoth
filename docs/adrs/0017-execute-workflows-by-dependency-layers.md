# ADR 0016: Execute Workflows by Dependency Layers

- Status: Accepted
- Date: 2026-08-07

## Context

Workflow specifications represent directed acyclic graphs (DAGs) of independently configured workflow steps.

Executing workflow steps sequentially according to declaration order would introduce behavior that depends on implementation details rather than workflow topology.

Independent workflow steps should execute as though they were evaluated concurrently, even if the initial implementation executes them sequentially.

Workflow execution therefore requires deterministic semantics that remain valid as future implementations introduce parallel execution.

## Decision

Workflow candidates are executed one dependency layer at a time.

Each workflow step within a dependency layer receives the same immutable layer-start context.

Workflow step outputs are merged only after every workflow step in the layer has completed successfully.

Workflow step outputs are merged in declared workflow order to ensure deterministic execution.

If any workflow step within a dependency layer fails, workflow execution terminates immediately.

No outputs produced by the failed dependency layer are merged into workflow context.

Previously completed dependency layers remain committed.

Workflow execution records every successfully executed workflow step together with its execution result and dependency layer.

## Consequences

### Positive

- Workflow execution semantics are independent of execution order.
- Future parallel execution does not change workflow behavior.
- Context propagation is deterministic.
- Workflow execution remains reproducible.
- Dependency layers provide natural transaction boundaries.
- Workflow orchestration remains independent from strategy execution.

### Negative

- Independent workflow steps currently execute sequentially even though they are semantically concurrent.
- Failed dependency layers discard successful sibling results.

## Alternatives Considered

### Execute workflow steps sequentially

Rejected because sequential execution allows sibling workflow steps to observe one another's outputs.

### Merge workflow outputs immediately

Rejected because workflow behavior would depend on execution ordering rather than dependency topology.

### Execute all workflow steps concurrently

Rejected because dependency relationships define explicit execution ordering.

Parallel execution should only occur within dependency layers while preserving deterministic context propagation.