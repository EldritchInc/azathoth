# ADR 0031: Workflow Optimization Boundary

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow execution, evaluation, scoring, ranking, and experimentation produce deterministic evidence describing workflow performance.

Optimization systems require a mechanism for generating subsequent workflow populations using this evidence.

Optimization should remain independent of workflow execution details.

Execution systems should not contain optimization algorithms.

A clear architectural boundary is required between workflow experimentation and workflow optimization.

## Decision

Workflow optimization is established as a separate top-level domain.

Workflow optimization consumes:

- workflow experiment results; and
- workflow candidate populations.

Workflow optimization produces immutable optimization results describing the next workflow generation.

The initial optimizer implementation is `ReplayWorkflowOptimizer`.

Replay optimization intentionally performs no candidate modification.

It exists solely to establish and validate the optimization boundary independently of future optimization algorithms.

## Consequences

### Positive

- Workflow execution and optimization remain independently evolvable.
- Optimization algorithms share a common interface.
- Workflow experiments remain focused on empirical observation.
- Candidate generation becomes replaceable without affecting workflow execution.
- Future optimization algorithms can be introduced without changing experiment orchestration.

### Negative

- Optimization introduces an additional architectural layer.
- The initial replay optimizer intentionally performs no optimization.

## Alternatives Considered

### Embed optimization into workflow experiments

Rejected because experiments observe workflow behavior while optimization generates future candidates.

### Implement evolutionary optimization immediately

Rejected because architectural boundaries should be established before introducing optimization heuristics.

A deterministic replay optimizer validates the optimization contract while keeping optimization behavior independent from execution.