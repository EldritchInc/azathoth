# ADR 0030: Workflow Experiments

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow execution produces durable workflow runs.

Workflow evaluation summarizes execution correctness.

Workflow scorecards normalize workflow quality according to a scoring policy.

Workflow rankings deterministically compare multiple workflow scorecards.

Optimization systems require a reusable orchestration layer capable of executing multiple workflow candidates, evaluating them, scoring them, and selecting the strongest result.

This orchestration should remain independent of optimization algorithms.

## Decision

Workflow experiments provide deterministic orchestration for comparing multiple workflow candidates.

A workflow experiment:

- executes every supplied workflow candidate;
- evaluates every workflow result;
- scores every workflow evaluation;
- ranks every workflow scorecard; and
- exposes the winning workflow scorecard.

Workflow experiments introduce no optimization logic.

They execute existing workflow infrastructure while preserving immutable experiment results.

## Consequences

### Positive

- Workflow comparison becomes reusable.
- Optimization algorithms remain focused on candidate generation.
- Execution, evaluation, scoring, and ranking remain independently testable.
- Experiment results are deterministic and immutable.
- Future optimization systems can reuse workflow experiments without duplicating orchestration.

### Negative

- Workflow experiments introduce another orchestration layer.
- Experiment execution requires every workflow candidate to be evaluated.

## Alternatives Considered

### Allow optimization systems to orchestrate workflow execution directly

Rejected because execution orchestration would become duplicated across optimization implementations.

### Embed experiment behavior inside the workflow runner

Rejected because workflow runners execute one workflow while experiments compare many workflows.

Separating these responsibilities preserves a clean execution architecture.