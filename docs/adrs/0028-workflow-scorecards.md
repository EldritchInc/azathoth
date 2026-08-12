# ADR 0028: Workflow Scorecards

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow execution records durable execution history.

Workflow evaluation provides objective observations describing execution quality, reliability, latency, and cost.

Optimization systems require a normalized representation that expresses how desirable a workflow execution was according to a scoring policy.

Scoring policies are inherently subjective and may evolve over time without changing workflow execution or evaluation.

## Decision

Workflow evaluations are converted into immutable workflow scorecards.

A workflow scorecard packages:

- quality score;
- reliability score;
- latency score;
- cost score;
- overall score; and
- scoring rationale.

All scores are normalized to the range:

- 0.0 = worst
- 1.0 = best

Workflow scorecards are produced by deterministic scoring policies.

Scoring policies operate entirely on durable execution records and objective workflow evaluations.

Workflow execution remains independent of optimization strategy.

Different scoring policies may coexist without affecting workflow execution or evaluation.

## Consequences

### Positive

- Execution remains independent of optimization.
- Objective evaluation and subjective scoring are cleanly separated.
- Scorecards provide a stable optimization interface.
- Multiple scoring policies can coexist.
- Future optimization algorithms can compare workflows using normalized dimensions.

### Negative

- Scorecards introduce another derived model.
- Different optimization objectives may require different scoring policies.

## Alternatives Considered

### Store optimization scores directly in workflow evaluations

Rejected because evaluations are intended to remain objective observations of execution.

### Embed optimization heuristics inside workflow execution

Rejected because execution should remain deterministic and independent of optimization policy.

Separating execution, evaluation, and scoring allows each layer to evolve independently.