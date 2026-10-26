# ADR 0085: Report Judge Cost Beside Scorecards, Never in Them

- Status: Accepted
- Date: 2026-10-23
- Decided in: #97, #102

## Context

Semantic judging (ADR 0074) spends provider calls. That cost is real and
operators need to see it. It is not, however, a cost of the workflow being
judged: judges never run in production.

If judge cost entered a candidate's cost, a candidate would score worse merely
because its benchmark used an expensive judge, and optimization would favor
candidates for reasons unrelated to how they behave.

## Decision

Judge calls and their cost live only in evaluation evidence: `judge_calls`
evidence items, read by `judge_call_count` and `judge_calls_cost_usd`.

They never enter a `WorkflowRun`, a run's cost, a benchmark's total cost, or
any scorecard. `WorkflowScorer` takes cost from step metrics only, so
optimizing against an expensive judge and a free one produces identical
scorecards.

Judge numbers are reported beside the numbers they must not change:

- benchmark results and saved benchmark executions, per case and in total
- experiment evidence and records, per candidate and per case
- `workflow optimize`, in total and per generation
- `experiment show`, per observation, when any judge was called

Count and cost fields default to zero and are displayed only when non-zero,
so records written before them never show a misleading zero (ADR 0077).

## Consequences

### Positive

- Rankings reflect workflow behavior only.
- Operators still see what judging cost.

### Negative

- The total cost of an optimization session is spread across two kinds of
  figures, workflow cost and judge cost.

## Alternatives Considered

### Include judge cost in candidate cost

Rejected. The benchmark's judge would influence which candidate wins.

### Hide judge cost entirely

Rejected. It is real spending, and operators must be able to see it.
