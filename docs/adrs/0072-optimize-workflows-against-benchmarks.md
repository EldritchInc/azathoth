# ADR 0072: Optimize Workflows Against Benchmarks

- Status: Accepted
- Date: 2026-10-23
- Decided in: #96

## Context

`workflow optimize` originally judged candidates against one expected value
given on the command line. A candidate could then win by answering one example
well, and the expected value lived in shell history rather than in durable,
reviewable configuration.

Benchmark datasets (ADR 0049) already hold reusable cases with inputs,
expected outcomes and comparisons.

## Decision

Optimization is judged against a benchmark, never a single value:

```bash
azathoth workflow optimize <WORKFLOW_ID> \
    --benchmark <BENCHMARK_ID> \
    --target-latency <SECONDS> \
    --target-cost <USD>
```

There is no `--expected` option. What counts as correct belongs to the
benchmark's cases.

Every generation of a session is judged against the same dataset.
`WorkflowExperimentRunner` runs every candidate against every case. Each case's
input reaches the run as the canonical input event (ADR 0067), and the
candidate's declared result (ADR 0071) is judged with that case's own
comparison (ADR 0070).

Per-case scorecards are combined with `aggregate_workflow_scorecards`, the
same per-dimension mean that benchmark comparison uses. Each candidate enters
the ranking with one scorecard reflecting the whole benchmark, and the
model-substitution optimizer expands from the candidate that performed best
across it.

Before any candidate executes, the runner rejects an empty dataset, any
unsupported comparison, and any candidate without a declared result, so a
benchmark never runs partway.

## Consequences

### Positive

- Candidates win by performing well across many inputs.
- What counts as correct is durable, versioned configuration.
- Optimization and benchmark comparison score candidates the same way.

### Negative

- Optimization requires a benchmark to exist first.
- Cost grows with the number of cases times candidates times generations.

## Alternatives Considered

### Keep a single expected value as an alternative

Rejected. Two ways to judge would produce incomparable evidence.

### Rank on a different aggregate than benchmark comparison

Rejected. The same candidate would rank differently depending on which
command judged it.
