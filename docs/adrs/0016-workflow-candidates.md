# ADR 0016: Generate Executable Workflow Candidates

- Status: Accepted
- Date: 2026-08-06

## Context

Workflow specifications describe durable, provider-neutral AI workflows.

Before a workflow can execute, each workflow step must be transformed into an executable strategy by binding it to an appropriate language model.

This transformation should preserve the workflow's structure while introducing runtime execution objects.

## Decision

Azathoth introduces `WorkflowCandidate` as the executable counterpart to `WorkflowSpecification`.

Workflow candidate generation transforms each workflow step specification into an executable strategy using the existing prompt candidate generation pipeline.

A workflow candidate preserves:

- workflow metadata;
- workflow step ordering;
- workflow dependency relationships; and
- step-scoped model requirements.

Each executable workflow step contains:

- the workflow step identifier;
- dependency relationships; and
- an executable strategy.

Workflow candidates are runtime objects rather than durable configuration.

Accordingly, workflow candidates are implemented as immutable dataclasses rather than serializable Pydantic models.

## Consequences

### Positive

- Workflow specifications remain provider-neutral.
- Runtime execution concerns remain separate from durable configuration.
- Existing prompt candidate generation is reused.
- Workflow topology is preserved during candidate generation.
- Different workflow steps may bind to different language models.
- Future workflow runners operate on executable workflow candidates rather than specifications.

### Negative

- Workflow candidate generation introduces an additional transformation step before execution.

## Alternatives Considered

### Execute workflow specifications directly

Rejected because durable specifications should remain independent of runtime provider implementations.

### Bind one language model to an entire workflow

Rejected because different workflow steps frequently require different language models, context windows, capabilities, and execution policies.

### Represent workflow candidates as serializable models

Rejected because executable strategies contain runtime objects that should not become part of durable workflow configuration.