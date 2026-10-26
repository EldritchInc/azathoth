# ADR 0075: Save Benchmark Executions

- Status: Accepted
- Date: 2026-10-23
- Decided in: #98

## Context

`benchmark run` and `benchmark compare` spend provider calls, and judge calls,
to produce evidence. Before this decision, that evidence existed only as
terminal output. A ranking could not be explained later, and a regression
could not be traced to the runs that showed it.

## Decision

Every `benchmark run` and `benchmark compare` is saved. There is no opt-in
flag.

`WorkflowBenchmarkExecutionRecord` holds one execution:

- the benchmark and the content digest of the exact revision executed
- its kind, `run` or `compare`
- one candidate per workflow, identified by workflow ID and candidate
  signature, with one case per benchmark case in dataset order: the
  comparison, run, evaluation, outcome, run failure, and judge calls and cost
- for `compare`, each candidate's scorecard, the ranking, and the scoring
  policy (`--target-latency`, `--target-cost`) that produced it

`WorkflowBenchmarkEvidenceRecorder` builds and validates the whole record
before saving anything, then saves every case run, every evaluation, and the
record. Evidence that cannot form a valid record leaves every repository
unchanged. Records are saved without replacing, through
`WorkflowBenchmarkExecutionRepository`.

Nothing is saved when execution is rejected before any case runs, or when
judging fails.

Each candidate is generated once before any case executes, so a record
describes exactly one resolved configuration.

The CLI lists records with `benchmark executions` and shows one with
`benchmark execution-show`. `benchmark compare` also breaks results down per
comparison.

## Consequences

### Positive

- Every benchmark result can be explained and revisited.
- A saved ranking carries the policy that produced it.
- Records name the exact benchmark revision they judged.

### Negative

- Every benchmark invocation writes records, including exploratory ones.

## Alternatives Considered

### Save only when asked

Rejected. Evidence that cost provider calls to produce should not depend on
remembering a flag.

### Save summaries without runs and evaluations

Rejected. A summary cannot be audited.
