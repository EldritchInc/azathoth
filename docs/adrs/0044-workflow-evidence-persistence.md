# ADR 0044: Persist Execution Evidence Separately From Later Judgments

- Status: Accepted
- Date: 2026-08-18

## Context

Azathoth records completed workflow execution in `WorkflowRun`.

A workflow run contains the observable result of executing one workflow
candidate, including:

- workflow metadata;
- workflow step results;
- execution attempts;
- failures;
- strategy execution results;
- workflow values;
- initial context;
- final context;
- start time; and
- completion time.

Derived statistics and reliability metrics are computed from this recorded
execution evidence.

```text
WorkflowRunner
      │
      ▼
WorkflowRun
      │
      ├── WorkflowStepRun
      │      ├── ExecutionResult
      │      ├── WorkflowStepAttempt
      │      └── WorkflowValue
      │
      ├── Context
      └── timestamps
```

Applications also need to record judgments made after execution.

Examples include:

- an evaluator determining whether an output was correct;
- a human marking a production result as good or bad;
- an application recording why a result was unacceptable; and
- supplying a corrected output.

These later judgments must not rewrite the original execution record.

## Decision

`WorkflowRun` is the durable raw execution-evidence artifact.

Each workflow run has a stable identifier.

```text
WorkflowRun
├── id
├── workflow
├── steps
├── initial_context
├── final_context
├── started_at
└── completed_at
```

Workflow runs may be persisted using `WorkflowRunRepository`.

Current implementations include:

```text
WorkflowRunRepository
        │
        ├── InMemoryWorkflowRunRepository
        │
        └── SQLiteWorkflowRunRepository
```

Persisted workflow runs are append-only.

Saving another run with the same identifier is rejected.

## Run Identity

A stable run identifier provides the durable anchor for evidence associated with
one execution.

```text
WorkflowRun(id)
      │
      ├── evaluator judgments
      ├── human feedback
      ├── application feedback
      └── other run-linked evidence
```

The workflow identifier answers:

> Which workflow was executed?

The run identifier answers:

> Which specific execution are we talking about?

Those identities are distinct.

## Raw Evidence

`WorkflowRun` records what happened.

It is not updated when later systems disagree with or reinterpret the result.

```text
execution
   │
   ▼
WorkflowRun
   │
   ▼
immutable raw evidence
```

Derived statistics and reliability metrics are not duplicated into persistence.

They remain deterministic projections of the persisted run.

```text
persisted WorkflowRun
        │
        ├── statistics
        └── reliability
```

Reconstructing the raw run therefore reconstructs the source evidence from which
those derived values are computed.

## Feedback

Human or application judgment is represented separately by
`WorkflowRunFeedback`.

```text
WorkflowRunFeedback
├── id
├── run_id
├── disposition
├── reason
├── corrected_output
└── created_at
```

Feedback dispositions are:

- `good`; and
- `bad`.

Bad feedback requires a reason.

Corrected output is optional.

This allows a caller to record:

```text
run_id: ...
disposition: bad
reason: "The classification was incorrect."
corrected_output: "negative"
```

without changing the original recorded output.

## Feedback Persistence

Feedback has its own persistence boundary.

```text
WorkflowRunFeedbackRepository
        │
        ├── InMemoryWorkflowRunFeedbackRepository
        │
        └── SQLiteWorkflowRunFeedbackRepository
```

Feedback records are append-only.

Multiple feedback records may reference the same workflow run.

This preserves feedback history rather than reducing a run to one mutable label.

## Separation of Observation and Judgment

Azathoth keeps raw execution and later interpretation distinct.

```text
WorkflowRun
"What happened?"

EvaluationResult
"What did an evaluator conclude?"

WorkflowRunFeedback
"What did a human or application conclude?"
```

These judgments may disagree.

For example:

```text
EvaluationResult
    PASSED

WorkflowRunFeedback
    BAD
    "Technically correct, but the response violated a required format."
```

The disagreement itself is evidence.

Azathoth does not collapse these artifacts into one mutable result.

## SQLite Representation

`SQLiteWorkflowRunRepository` persists the serialized `WorkflowRun` together
with queryable run and workflow identifiers.

```text
WorkflowRun
    │
    ▼
model_dump_json()
    │
    ▼
workflow_runs
    │
    ▼
model_validate_json()
    │
    ▼
WorkflowRun
```

The workflow identifier is also stored separately to support efficient retrieval
of executions belonging to one workflow.

`SQLiteWorkflowRunFeedbackRepository` similarly persists feedback while storing
its run identifier separately for efficient lookup.

```text
workflow_runs
     │
     │ run_id
     ▼
workflow_run_feedback
```

The serialized model payload remains the canonical domain representation.

## Production Evidence Lifecycle

A production workflow execution can now follow this lifecycle:

```text
WorkflowSpecification
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun(id)
        │
        ▼
WorkflowRunRepository
        │
        ▼
durable raw evidence
        │
        ├───────────────┐
        ▼               ▼
EvaluationResult   WorkflowRunFeedback
                      │
                      ├── good / bad
                      ├── reason
                      └── corrected output
```

A later feedback write does not modify the persisted workflow run.

## Consequences

### Positive

- Production executions have stable durable identity.
- Raw execution evidence survives process restarts.
- Workflow executions can be queried by workflow identifier.
- Feedback can be attached after execution.
- Corrected outputs can be recorded without overwriting observed outputs.
- Multiple judgments can coexist for one run.
- Evaluator and human judgments remain distinct.
- Statistics and reliability remain derived from canonical raw evidence.
- Persistence introduces no workflow execution changes.

### Negative

- Run and feedback repositories must be queried separately when both artifacts
  are needed.
- Feedback persistence does not currently enforce referential integrity against
  a workflow run repository.
- SQLite stores complete domain payloads rather than normalized execution
  tables.
- Large execution contexts may eventually require additional storage policy.
- Retention, archival, and redaction policy are not defined by this decision.

## Alternatives Considered

### Add Feedback Fields Directly to WorkflowRun

Rejected.

`WorkflowRun` records what happened during execution.

Later judgment must not mutate historical execution evidence.

### Replace Raw Output With Corrected Output

Rejected.

A corrected value describes what should have happened.

It must not replace the value that actually occurred.

### Store Only Scorecards

Rejected.

`WorkflowScorecard` is derived interpretation.

It does not contain the complete execution trace needed to reconstruct what
happened.

### Store Only EvaluationResult

Rejected.

Evaluation records one form of correctness judgment.

It does not contain the workflow execution evidence being judged and does not
represent arbitrary human or application feedback.

### Use One Mutable Feedback Record Per Run

Rejected.

Multiple observers or later corrections may produce multiple judgments.

Append-only feedback preserves that history.

### Persist Derived Statistics and Reliability

Rejected.

Those values are deterministic projections of `WorkflowRun`.

Persisting both source evidence and derived projections would create redundant
state that could become inconsistent.

## Result

Azathoth now separates durable observation from durable judgment.

```text
                    WorkflowRunner
                          │
                          ▼
                   WorkflowRun(id)
                          │
                          ▼
                WorkflowRunRepository
                          │
                    durable truth
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
      EvaluationResult        WorkflowRunFeedback
      evaluator judgment      human/app judgment
                                      │
                               ┌──────┼──────┐
                               ▼      ▼      ▼
                              good   reason correction
                               /
                              bad
```

The recorded execution remains immutable regardless of what later judgments say
about it.

Workflow evidence persistence introduces no optimization policy.