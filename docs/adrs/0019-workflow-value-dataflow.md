# ADR 0019: Explicit Workflow Value Dataflow

- Status: Accepted
- Date: 2026-08-09

## Context

Workflow execution frequently requires passing structured information from one workflow step to another.

Examples include:

- classifications;
- retrieved documents;
- confidence scores;
- routing decisions; and
- intermediate reasoning.

Passing these values implicitly through execution context obscures workflow dependencies and makes workflows difficult to validate.

Workflow dataflow should therefore be explicitly declared and statically validated.

## Decision

Workflow steps explicitly export structured outputs using `WorkflowValueBinding`.

Workflow values are identified by the combination of:

- producing workflow step; and
- exported workflow value name.

Downstream workflow steps declare required inputs using `WorkflowInputBinding`.

Each input references a specific exported workflow value using `WorkflowValueReference`.

Workflow specifications validate that:

- referenced producer steps exist;
- referenced output names exist;
- referenced producer steps are upstream in the workflow dependency graph;
- producer output names are unique within a workflow step; and
- consumer input names are unique within a workflow step.

During execution, workflow input bindings resolve against committed workflow values and are made available only within the execution context of the consuming workflow step.

Workflow input bindings are not persisted within shared workflow context.

## Consequences

### Positive

- Workflow dataflow is explicit.
- Invalid workflows fail during validation.
- Runtime execution becomes deterministic.
- Workflow context remains independent from workflow value propagation.
- Multiple workflow steps may export values with identical names.
- Workflow values become suitable for routing and conditional execution.

### Negative

- Workflow specifications require explicit input and output declarations.
- Additional validation is performed during workflow construction.

## Alternatives Considered

### Pass workflow values through shared context

Rejected because execution history and workflow data represent different concepts.

### Resolve workflow values dynamically without declarations

Rejected because invalid workflows would fail during execution rather than validation.

### Require globally unique workflow value names

Rejected because workflow value identity is intentionally scoped to the producing workflow step.