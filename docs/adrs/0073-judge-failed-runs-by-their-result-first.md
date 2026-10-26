# ADR 0073: Judge Failed Runs by Their Result First

- Status: Accepted
- Date: 2026-10-23
- Decided in: #96

## Context

ADR 0066 keeps failed candidates in the ranking. That leaves two questions:
what counts as a failed run for judging purposes, and how a failed run
scores.

Steps may fail by design. Under the `continue` and `skip_dependents` policies,
a workflow with redundant producers is expected to tolerate failures and still
answer. Penalizing it as failed would punish the resilience it was built for.

Scoring is the other risk. A run that crashes immediately is fast and cheap.
If it earned latency and cost credit, a candidate that always crashed could
outrank a correct but slower one.

## Decision

A run is judged by its declared result first:

```text
declared result produced?
    yes ──► judged with the case's comparison, even if some steps failed
    no, and a step failed ──► evaluate_failed_run
    no, and no step failed ──► WorkflowResultError
```

`evaluate_failed_run` returns a failing evaluation from the evaluator
`workflow-run-failure` 1.0.0, with score `0.0`, naming the first failed step
and its final failure:

```text
Workflow run failed at step <STEP_ID>: <failure message>
```

It is persisted and rendered like any other evaluation, and benchmark results
count it under `run_failures`.

`WorkflowScorer` gives a run judged this way no latency or cost credit.
Failing quickly and cheaply is not efficiency.

A run that tolerated failures but still produced its result is judged on that
result. Its reliability score still reflects the failed steps.

A failed run on a semantic case never reaches a judge.

## Consequences

### Positive

- Redundant workflows are judged on their answers.
- A crashing candidate can never win on speed or price.
- Run failures are distinguishable from wrong answers in every result.

### Negative

- A run that silently produced a wrong answer and a run that crashed both
  score zero quality; only the evaluator name tells them apart.

## Alternatives Considered

### Fail any run in which a step failed

Rejected. Tolerated failures are a designed behavior.

### Score failed runs on latency and cost like any other

Rejected. Crashing would become a winning strategy.
