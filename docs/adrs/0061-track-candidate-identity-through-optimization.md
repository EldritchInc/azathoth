# ADR 0061: Track Candidate Identity Through Optimization

- Status: Accepted
- Date: 2026-09-01
- Decided in: #67

## Context

An experiment produces evidence about a population of executable workflow
candidates. An optimizer then proposes the next population from that
evidence.

For that to be sound, every piece of evidence must name exactly which
candidate produced it, and the optimizer must start from the candidate the
ranking actually chose. Matching evidence to candidates by position or by
workflow ID alone is ambiguous once several candidates share a workflow.

## Decision

Workflow experiment evidence identifies its candidate through
`WorkflowCandidateSignature`.

This builds on the deterministic identities that generated prompt strategies
already receive:

```text
uuid5(specification strategy ID, provider-qualified model identifier)
```

so the same specification bound to the same model always produces the same
strategy identity, across processes and experiments.

The optimization package reconnects evidence with candidates explicitly:

- `resolve_workflow_candidate`
- `resolve_workflow_experiment_evidence`
- `resolve_workflow_experiment_winner`

Resolution requires exactly one matching candidate. A missing or ambiguous
match fails explicitly.

The ranking identifies the empirical winner. The optimizer decides what to
propose from it, and never redefines which candidate won.

## Consequences

### Positive

- Evidence, rankings and proposals agree on candidate identity.
- Identical bindings are recognizable across experiments.
- Ambiguity is an error rather than a silent mismatch.

### Negative

- Candidates whose signatures collide cannot be optimized until they are
  distinguishable.

## Alternatives Considered

### Match evidence to candidates by population order

Rejected. Order is an implementation detail and changes between generations.

### Let the optimizer choose its own winner

Rejected. Ranking would stop being the authority on empirical results.
