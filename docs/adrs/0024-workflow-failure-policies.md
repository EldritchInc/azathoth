# ADR 0024: Workflow Failure Policies

- Status: Accepted
- Date: 2026-08-12

## Context

Workflow retry policies allow transient failures to be retried.

However, not every failure should terminate an entire workflow.

Different workflow steps have different operational requirements.

Examples include:

- required classification steps;
- optional enrichment steps;
- best-effort metadata extraction; and
- independent execution branches.

Failure handling should therefore be configurable independently for each workflow step.

Retry behavior answers:

> How many times should execution be attempted?

Failure policy answers:

> What should happen if execution never succeeds?

These are separate orchestration concerns.

## Decision

Workflow steps may now declare a `WorkflowFailurePolicy`.

Failure policies are immutable and become part of the durable workflow specification.

The supported policies are:

- `FAIL_WORKFLOW`
- `CONTINUE`
- `SKIP_DEPENDENTS`

### FAIL_WORKFLOW

Abort workflow execution immediately after retries are exhausted.

The original exception is propagated to the caller.

### CONTINUE

Record the failed workflow step while allowing remaining workflow execution to continue.

Failed workflow steps do not produce workflow values.

Downstream steps continue to participate in workflow execution.

If a downstream step requires workflow values that were never produced, existing workflow value and condition evaluation naturally prevent execution.

### SKIP_DEPENDENTS

Record the failed workflow step.

Transitively skip every workflow step that depends upon the failed step.

Independent branches continue executing normally.

## Consequences

### Positive

- Failure handling becomes configurable per workflow step.
- Retry behavior and failure handling remain independent concepts.
- Failed workflow steps become durable workflow artifacts.
- Independent workflow branches continue whenever appropriate.
- Workflow orchestration becomes fault tolerant without increasing strategy complexity.

### Negative

- Workflow execution semantics become more expressive.
- Workflow runs may now contain executed, failed, and skipped workflow steps simultaneously.

## Alternatives Considered

### Always abort workflow execution

Rejected because many workflow steps are optional or belong to independent execution branches.

### Retry indefinitely

Rejected because retry behavior and failure handling solve different problems.

Retries address transient failures.

Failure policies address permanent failures.

### Encode failure handling inside strategies

Rejected because failure handling is orchestration behavior rather than strategy behavior.

Keeping failure policies within workflow execution preserves simple strategy implementations while allowing execution policies to evolve independently.