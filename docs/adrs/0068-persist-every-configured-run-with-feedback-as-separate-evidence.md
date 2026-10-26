# ADR 0068: Persist Every Configured Run, With Feedback as Separate Evidence

- Status: Accepted
- Date: 2026-10-02
- Decided in: #90, #91

## Context

ADR 0056 introduced `workflow run`, and recorded as a known limitation that the
CLI did not persist the runs it executed. Operators could see a run once, in
the terminal, and never again.

ADR 0044 established that execution evidence and later judgments are separate
records. The CLI offered no way to record a judgment.

Without durable configured runs, there is nothing to inspect, judge, or later
turn into benchmark cases.

## Decision

Every completed configured run is persisted, whether it succeeded or failed.
Only a failure before any run exists, such as candidate generation failing,
persists nothing.

Configured, benchmark, experiment and production runs share one run history.
A run's source is derived from its associations, not from separate storage:

```text
associated with a ProductionInvocation        production
observed by a WorkflowExperimentRecord        experiment
recorded by a benchmark execution record      benchmark
otherwise                                     configured
```

Production takes precedence over every other association, and experiment over
benchmark.

The CLI reads that history with `workflow runs` and `run show`.

Operators judge runs with `run feedback`, which saves a `WorkflowRunFeedback`
record:

```text
--good                                   the run was right
--bad --reason <TEXT>                    the run was wrong, and why
--bad --reason <TEXT> --corrected-output <JSON>
                                         and what it should have produced
```

A corrected output is accepted only with `--bad`, and `--bad` requires a
non-blank reason.

Recording feedback never changes the run, the workflow specification, or
production state.

## Consequences

### Positive

- Every run can be revisited, judged and traced.
- One history serves every source, with no duplicated storage.
- Judgments are durable evidence rather than terminal output.

### Negative

- Run history grows with every configured run.
- A correction to JSON null cannot be recorded, because a null corrected
  output means no correction. `benchmark add-case --expected null` is the
  workaround.

## Alternatives Considered

### Persist only failed runs, or only when asked

Rejected. Evidence would depend on the operator predicting what matters.

### Store runs separately per source

Rejected. A run's meaning comes from what it is associated with, and separate
stores would duplicate one concept.
