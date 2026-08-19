# ADR 0045: Associate Durable Evaluations With Workflow Runs

- Status: Accepted
- Date: 2026-08-19

## Context

Azathoth separates workflow execution from evaluation.

A `WorkflowRun` records what happened during one workflow execution.

An `EvaluationResult` records an evaluator's judgment about whether an observed
result satisfied an expected outcome.

```text
WorkflowRun
"What happened?"

EvaluationResult
"Did the observed result satisfy the expectation?"
```

`EvaluationResult` is intentionally independent of workflow execution.

This allows evaluators to operate on arbitrary expected and actual values
without depending on workflow runtime concepts.

Production and other durable workflow executions nevertheless need to retain the
relationship between a specific workflow run and evaluations performed against
that run.

That relationship must survive process restarts without adding workflow
concerns to the evaluation domain or modifying the original execution record.

## Decision

Azathoth represents the relationship between a durable workflow run and one
evaluator judgment using `WorkflowRunEvaluation`.

```text
WorkflowRunEvaluation
├── run_id
├── evaluation
└── evaluated_at
```

The embedded `EvaluationResult` remains the canonical evaluator judgment.

`WorkflowRunEvaluation` adds only the workflow-run relationship and the time at
which the evaluation was associated with the run.

## Identity

`EvaluationResult` already has a stable identifier.

`WorkflowRunEvaluation` therefore uses the embedded evaluation identifier as its
own durable identity.

```text
WorkflowRunEvaluation.id
          │
          ▼
EvaluationResult.id
```

A second identifier for the same evaluator judgment is not introduced.

The run identifier answers:

> Which execution was evaluated?

The evaluation identifier answers:

> Which evaluator judgment is this?

## Dependency Direction

The evaluation package remains independent of workflows.

```text
azathoth.evaluation
        │
        ▼
EvaluationResult

        ▲
        │
azathoth.workflows
        │
        ▼
WorkflowRunEvaluation
```

`EvaluationResult` does not reference `WorkflowRun`.

The workflow layer owns the association because it is the layer that knows about
durable workflow execution identity.

## Multiple Evaluations

A workflow run may have multiple independent evaluator judgments.

```text
WorkflowRun
    │
    ├── exact-match evaluation
    ├── schema evaluation
    ├── format evaluation
    └── other evaluation
```

These evaluations are not collapsed into one mutable result.

Each retains its own:

- evaluator identity;
- evaluator version;
- score;
- threshold;
- status;
- reason; and
- structured evidence.

## Persistence

`WorkflowRunEvaluationRepository` provides a storage-neutral persistence
boundary.

Current implementations include:

```text
WorkflowRunEvaluationRepository
        │
        ├── InMemoryWorkflowRunEvaluationRepository
        │
        └── SQLiteWorkflowRunEvaluationRepository
```

Run evaluations are append-only.

Saving another run evaluation with the same evaluation identifier is rejected.

SQLite persistence stores queryable evaluation and run identifiers alongside
the serialized domain artifact.

```text
WorkflowRunEvaluation
        │
        ▼
model_dump_json()
        │
        ▼
workflow_run_evaluations
        │
        ▼
model_validate_json()
        │
        ▼
WorkflowRunEvaluation
```

Evaluations belonging to one workflow run can be retrieved by `run_id` while
preserving insertion order.

## Durable Evidence Model

Workflow execution now supports three distinct evidence artifacts.

```text
                    WorkflowRun
                   "What happened?"
                    /         \
                   /           \
                  ▼             ▼
 WorkflowRunEvaluation     WorkflowRunFeedback
 "Machine judgment"        "Human/app judgment"
          │                       │
          ▼                       ▼
  EvaluationResult            good / bad
  score                       reason
  status                      corrected output
  reason
  evidence
```

These artifacts have different meanings.

### WorkflowRun

Records observed execution.

Examples include:

- executed steps;
- attempts;
- failures;
- outputs;
- workflow values;
- contexts; and
- timestamps.

### WorkflowRunEvaluation

Associates a specific execution with an evaluator-produced judgment.

The evaluator judgment may include:

- score;
- threshold;
- pass/fail status;
- reason; and
- structured evidence.

### WorkflowRunFeedback

Records a later human or application judgment.

Feedback may include:

- good/bad disposition;
- reason; and
- corrected output.

## Independent Judgments

Machine evaluation and human or application feedback are intentionally
independent.

For example:

```text
WorkflowRun
actual = "positive"

WorkflowRunEvaluation
expected = "negative"
status = FAILED

WorkflowRunFeedback
disposition = GOOD
reason = "The observed classification is acceptable for this request."
```

This state is valid.

The evaluator determined that the observed value did not satisfy its specified
expectation.

The feedback author independently determined that the observed result was
acceptable.

Neither judgment rewrites the other.

Neither judgment rewrites the original `WorkflowRun`.

## Evidence Immutability

Later evidence does not modify earlier evidence.

```text
WorkflowRun
     │
     ├──────────────► WorkflowRunEvaluation
     │
     └──────────────► WorkflowRunFeedback
```

Persisting an evaluation does not change the run.

Persisting feedback does not change the run.

Persisting feedback does not change an evaluation.

Persisting an evaluation does not change feedback.

This preserves the distinction between observation and interpretation.

## Consequences

### Positive

- Evaluator judgments survive process restarts.
- Evaluations are durably associated with specific executions.
- Multiple evaluations may coexist for one run.
- Full structured evaluator evidence is preserved.
- Evaluation remains independent of workflow runtime concepts.
- Machine and human judgments remain independent.
- Raw workflow execution evidence remains unchanged.
- Repository implementations remain storage-neutral.
- SQLite supports efficient lookup by run identity.

### Negative

- Applications must query separate repositories when they need execution,
  evaluation, and feedback together.
- Persistence does not currently enforce referential integrity between a run and
  its evaluations.
- SQLite stores complete serialized domain payloads rather than normalized
  evaluation fields.
- Retention and archival policy remain outside this decision.

## Alternatives Considered

### Add run_id to EvaluationResult

Rejected.

`EvaluationResult` is intentionally independent of workflow execution and may be
used outside workflows.

Adding workflow identity would reverse that architectural separation.

### Add evaluations directly to WorkflowRun

Rejected.

`WorkflowRun` records execution.

Evaluation occurs after execution and must not mutate the historical execution
record.

### Store only pass/fail status

Rejected.

An evaluator judgment contains more evidence than a boolean result.

Score, threshold, evaluator identity, reason, and structured evidence are
required to preserve the original judgment.

### Store only one evaluation per run

Rejected.

Different evaluators may judge different properties of the same execution.

One evaluation must not replace another.

### Reuse WorkflowRunFeedback for evaluator results

Rejected.

Evaluator-produced judgment and human or application feedback represent
different evidence sources and have different semantics.

## Result

Azathoth can now durably reconstruct:

```text
WorkflowSpecification
        │
        ▼
WorkflowRun
        │
        ├── WorkflowRunEvaluation
        │       └── EvaluationResult
        │
        └── WorkflowRunFeedback
```

The execution, machine judgment, and human or application judgment remain
independent immutable evidence linked by durable run identity.

Workflow evaluation persistence introduces no optimization policy.