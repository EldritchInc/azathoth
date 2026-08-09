# ADR 0018: Declare and Record Workflow Values

- Status: Accepted
- Date: 2026-08-08

## Context

Workflow steps frequently produce structured outputs that are useful to later workflow steps.

Examples include:

- classifications;
- confidence scores;
- retrieval results;
- tool outputs; and
- structured intermediate reasoning.

These values are distinct from workflow context.

Workflow context records evidence and execution history.

Workflow values represent named conclusions intentionally exported by workflow steps for later workflow processing.

Workflow execution therefore requires an explicit mechanism for declaring and recording exported workflow values.

## Decision

Workflow steps explicitly declare exported values using `WorkflowValueBinding`.

Each binding assigns a stable workflow value name to a path within the strategy execution output.

Bindings are preserved from workflow specification through executable workflow candidates.

During execution, bindings are resolved against the strategy output to produce immutable `WorkflowValue` records.

Workflow values are recorded within each `WorkflowStepRun`.

`WorkflowRun` exposes deterministic query methods for retrieving recorded values by workflow value name or producing workflow step.

Workflow values are not automatically inserted into workflow context.

## Consequences

### Positive

- Workflow outputs are explicitly declared.
- Workflow values remain deterministic.
- Workflow execution remains independent from execution output structure.
- Multiple workflow steps may export values with the same name.
- Workflow values remain durable and serializable.
- Future routing and branching can depend upon workflow values.

### Negative

- Workflow steps must explicitly declare exported values.
- Invalid bindings terminate workflow execution.

## Alternatives Considered

### Export the entire execution output automatically

Rejected because workflow outputs should be intentional rather than implicit.

### Insert workflow values directly into context

Rejected because workflow values and execution evidence serve different architectural purposes.

### Require globally unique workflow value names

Rejected because independent workflow steps may legitimately export values with identical names.