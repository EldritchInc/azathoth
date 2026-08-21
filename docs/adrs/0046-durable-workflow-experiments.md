# ADR 0046: Persist Workflow Experiment Provenance

- Status: Accepted
- Date: 2026-08-20

## Context

Azathoth can compare multiple workflow candidates using deterministic execution,
evaluation, scoring, and ranking.

```text
Workflow Candidates
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
        │
        ▼
Evaluator
        │
        ▼
EvaluationResult
        │
        ▼
WorkflowScorer
        │
        ▼
WorkflowScorecard
        │
        ▼
WorkflowRanker
```

`WorkflowExperimentResult` represents the immediate result of comparing workflow
executions.

It contains:

- workflow scorecards; and
- their resulting ranking.

A scorecard contains derived quality, reliability, latency, cost, and overall
scores.

Those derived values are useful for comparison, but they do not identify the
specific workflow execution or evaluator judgment that produced them.

Durable experiment history therefore requires additional provenance.

## Decision

Azathoth records completed experiment provenance using
`WorkflowExperimentRecord`.

```text
WorkflowExperimentRecord
├── id
├── observations
├── ranking
└── recorded_at
```

Each `WorkflowExperimentObservation` records:

```text
WorkflowExperimentObservation
├── workflow metadata
├── run_id
├── evaluation_id
└── scorecard
```

The experiment record does not embed complete workflow-run or evaluation
payloads.

Instead, it references those already-durable evidence artifacts by identity.

## Source Evidence

Workflow execution and evaluation already have independent durability
boundaries.

```text
WorkflowRun
    │
    ▼
WorkflowRunRepository

WorkflowRunEvaluation
    │
    ▼
WorkflowRunEvaluationRepository
```

Experiment observations reference those artifacts.

```text
WorkflowExperimentObservation
        │
        ├── run_id
        │      │
        │      ▼
        │  WorkflowRun
        │
        └── evaluation_id
               │
               ▼
       WorkflowRunEvaluation
```

This avoids duplicating complete execution traces and evaluator evidence inside
every experiment record.

## Experiment Identity

Each experiment has its own stable identifier.

```text
WorkflowExperimentRecord.id
```

Each observation is identified within the experiment by its workflow-run
identity.

Run identity is used rather than workflow identity because an experiment
compares specific executions.

The same workflow definition may be executed more than once.

Those executions remain distinct experiment observations because their run
identifiers are distinct.

## Ranking

Experiment ranking stores workflow-run identifiers in final ranked order.

```text
ranking = (
    best_run_id,
    second_run_id,
    third_run_id,
)
```

The ranking must:

- contain no duplicate run identifiers; and
- reference every experiment observation exactly once.

The first ranked run is the experiment winner.

```text
WorkflowExperimentRecord
        │
        ▼
ranking[0]
        │
        ▼
winning WorkflowExperimentObservation
```

## Scorecards

Each observation preserves the scorecard produced for that execution.

```text
WorkflowRun
      +
EvaluationResult
      │
      ▼
WorkflowScorer
      │
      ▼
WorkflowScorecard
```

A scorecard records the derived comparison evidence used by the experiment,
including:

- quality score;
- reliability score;
- latency score;
- cost score;
- overall score; and
- rationale.

The scorecard does not replace the underlying run or evaluation.

Those source artifacts remain independently durable.

## Persistence

`WorkflowExperimentRepository` provides a storage-neutral persistence boundary.

Current implementations include:

```text
WorkflowExperimentRepository
        │
        ├── InMemoryWorkflowExperimentRepository
        │
        └── SQLiteWorkflowExperimentRepository
```

Experiment records are append-only.

Persisting another experiment with the same identifier is rejected.

## SQLite Representation

SQLite stores the canonical serialized experiment record.

```text
WorkflowExperimentRecord
        │
        ▼
model_dump_json()
        │
        ▼
workflow_experiments
        │
        ▼
model_validate_json()
        │
        ▼
WorkflowExperimentRecord
```

Queryable provenance references are also stored separately.

```text
workflow_experiment_observations
├── experiment_id
├── workflow_id
├── run_id
└── evaluation_id
```

This supports efficient discovery without requiring every experiment payload to
be deserialized.

For example, persisted experiments can be queried by workflow identity.

## Durable Experiment Reconstruction

A durable experiment can be reconstructed after process restart and followed
back to the source evidence that produced its result.

```text
WorkflowExperimentRecord
        │
        ├── run_id
        │      │
        │      ▼
        │  WorkflowRunRepository
        │      │
        │      ▼
        │  WorkflowRun
        │
        └── evaluation_id
               │
               ▼
       WorkflowRunEvaluationRepository
               │
               ▼
       WorkflowRunEvaluation
               │
               ▼
       EvaluationResult
```

This preserves both the derived experiment outcome and its empirical
provenance.

## Derived Evidence Does Not Replace Source Evidence

Experiment scorecards and rankings are derived judgments.

They do not replace:

- workflow execution evidence; or
- evaluator evidence.

```text
source evidence
    │
    ├── WorkflowRun
    └── EvaluationResult
             │
             ▼
        Scorecard
             │
             ▼
          Ranking
```

If scoring policy or interpretation changes later, the historical source
evidence remains available independently from the historical scorecard and
ranking.

## WorkflowExperimentResult Versus WorkflowExperimentRecord

The two models serve different purposes.

### WorkflowExperimentResult

Represents immediate comparison output.

```text
WorkflowExperimentResult
├── scorecards
└── ranking
```

It is convenient orchestration output.

### WorkflowExperimentRecord

Represents durable experiment provenance.

```text
WorkflowExperimentRecord
├── experiment identity
├── workflow identities
├── run identities
├── evaluation identities
├── scorecards
├── ranking
└── recorded time
```

Persistence therefore targets the durable provenance model rather than relying
on transient orchestration output alone.

## Experiments Do Not Generate Candidates

Experiment persistence records completed comparisons.

It does not define how candidate workflows are produced.

```text
Supplied Candidates
        │
        ▼
Experiment
        │
        ▼
Durable Evidence
```

The experiment subsystem records:

- what was executed;
- how it was evaluated;
- how it was scored; and
- how the observations ranked.

It does not decide what candidate should be created next.

## Consequences

### Positive

- Experiment history survives process restarts.
- Rankings retain stable execution identity.
- Historical scorecards retain provenance.
- Source runs remain independently inspectable.
- Source evaluator judgments remain independently inspectable.
- Experiment payloads do not duplicate complete execution traces.
- Multiple executions of the same workflow remain distinguishable.
- Workflow-specific experiment history can be queried efficiently.
- Experiment persistence remains independent of candidate-generation policy.

### Negative

- Reconstructing complete experiment evidence may require querying multiple
  repositories.
- Persistence does not currently enforce database-level referential integrity
  between experiment references, runs, and evaluations.
- Historical scorecards remain historical derived judgments even if scoring
  policy changes later.
- SQLite stores the canonical experiment model as serialized JSON rather than a
  fully normalized relational representation.

## Alternatives Considered

### Persist WorkflowExperimentResult Directly

Rejected as the sole durable representation.

`WorkflowExperimentResult` contains scorecards and ranking but does not retain
the run and evaluation identities required to trace those derived values back
to their source evidence.

### Embed WorkflowRun in Every Observation

Rejected.

Workflow runs already have their own durable persistence boundary.

Embedding them would duplicate potentially large execution evidence.

### Embed EvaluationResult in Every Observation

Rejected.

Run-linked evaluations already have their own durable persistence boundary.

Embedding them would duplicate evaluator evidence and create multiple canonical
copies of the same judgment.

### Rank by Workflow Identifier

Rejected.

An experiment compares executions, not merely workflow definitions.

One workflow may be executed more than once, so workflow identity is not
sufficient to identify an experiment observation.

### Persist Only the Winner

Rejected.

The complete comparison population and ranking are part of the experiment
evidence.

Discarding losing observations would destroy the basis for the comparison.

## Result

Azathoth now has a durable experiment provenance chain.

```text
WorkflowSpecification
        │
        ▼
WorkflowRun
        │
        ▼
WorkflowRunEvaluation
        │
        ▼
WorkflowScorecard
        │
        ▼
WorkflowExperimentRecord
        │
        ▼
Persistent Storage
        │
   process restart
        │
        ▼
WorkflowExperimentRecord
        │
        ├──► exact WorkflowRun
        └──► exact EvaluationResult
```

Workflow experiment persistence records empirical comparison history.

It introduces no candidate-generation or optimization policy.