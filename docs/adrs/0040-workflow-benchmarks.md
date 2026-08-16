# ADR 0040: Workflow Benchmarks

- Status: Accepted
- Date: 2026-08-16

## Context

Workflow execution, evaluation, scorecards, and ranking provide objective
measurements for individual workflow executions.

Optimization systems should compare workflow candidates using representative
workloads rather than isolated executions.

Benchmark execution should reuse existing workflow execution, evaluation,
scorecard, and ranking infrastructure rather than introducing a parallel
evaluation pipeline.

## Decision

Azathoth introduces immutable benchmark datasets composed of benchmark cases.

Each benchmark case contains:

- input;
- expected outcome; and
- optional metadata.

Benchmark datasets execute workflow candidates using the existing workflow
runner.

Each benchmark execution produces:

- workflow runs;
- evaluation results; and
- benchmark execution summaries.

Benchmark scorecards are derived from existing workflow scorecards.

Benchmark ranking delegates to the existing workflow ranking system.

No benchmark-specific ranking policy is introduced.

## Consequences

### Positive

- Benchmarks reuse existing workflow infrastructure.
- Evaluation remains deterministic.
- Ranking policy remains centralized.
- New benchmark datasets require no framework changes.
- Future optimization systems can compare candidates using representative
  workloads.

### Negative

- Benchmark execution requires multiple workflow runs.
- Aggregate scorecards introduce another analytical layer.

## Alternatives Considered

### Benchmark-specific ranking

Rejected because ranking policy already exists.

Maintaining two ranking systems would create unnecessary duplication and risk
divergent optimization behavior.

### Compare raw benchmark accuracy only

Rejected because workflow quality already considers reliability, latency, and
cost in addition to evaluation quality.

Benchmark evaluation should preserve those dimensions.