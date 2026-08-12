# ADR 0029: Workflow Ranking

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow scorecards provide normalized quality, reliability, latency, cost, and overall scores for individual workflow executions.

Optimization systems require a deterministic mechanism for comparing multiple workflow executions and selecting the strongest candidate.

Ranking is a comparison concern rather than a scoring concern.

Separating ranking from scoring allows different optimization systems to reuse the same workflow scorecards while applying consistent ordering behavior.

## Decision

Workflow scorecards are ordered using immutable workflow rankings.

A workflow ranking contains:

- ranked workflow entries;
- consecutive ranking positions; and
- the highest-ranked workflow as the winner.

Ranking is deterministic.

Workflow scorecards are ordered by:

1. overall score;
2. quality score;
3. reliability score;
4. latency score;
5. cost score; and
6. original input order for exact ties.

Ranking introduces no additional heuristics beyond deterministic ordering.

Workflow execution, evaluation, and scoring remain unchanged.

## Consequences

### Positive

- Workflow comparison becomes deterministic.
- Ranking is separated from scoring.
- Optimization systems receive a stable comparison interface.
- Exact ties remain reproducible.
- Future optimization algorithms can consume rankings directly.

### Negative

- Workflow rankings are another derived model.
- Alternative ranking policies require separate ranking implementations.

## Alternatives Considered

### Compare workflow scorecards directly throughout optimization

Rejected because comparison behavior would become duplicated across optimization systems.

### Embed ranking inside workflow scorecards

Rejected because scorecards describe one workflow while rankings compare many workflows.

Separating the two responsibilities keeps both models simple and reusable.