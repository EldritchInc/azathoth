# ADR 0027: Workflow Evaluation

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow execution produces durable execution records.

Derived execution statistics summarize workflow behavior.

Derived reliability metrics normalize execution behavior across workflows of different sizes.

Optimization systems, benchmarking tools, dashboards, and future adaptive workflow planners should not depend directly on workflow execution internals.

A stable evaluation model provides a consistent interface between execution and higher-level analysis.

## Decision

Workflow runs expose immutable workflow evaluations.

A workflow evaluation packages:

- workflow identity;
- execution statistics;
- reliability metrics; and
- evaluation timestamp.

Workflow evaluations are derived entirely from recorded workflow execution.

Workflow evaluations contain no duplicated execution state and introduce no additional scoring or heuristics.

Evaluation models remain objective observations of workflow execution.

Interpretation and optimization remain responsibilities of higher-level components.

## Consequences

### Positive

- Execution and optimization remain cleanly separated.
- Consumers receive a stable evaluation interface.
- Evaluation remains deterministic.
- No duplicated execution state is introduced.
- Future optimization systems can evolve independently of execution internals.

### Negative

- Evaluations are recomputed when requested.
- Additional evaluation models become part of the public API.

## Alternatives Considered

### Expose workflow execution directly

Rejected because higher-level systems would become tightly coupled to execution internals.

### Add optimization scores directly to evaluations

Rejected because scoring policies evolve independently of execution.

Keeping evaluations objective allows multiple optimization strategies to coexist without changing the execution model.