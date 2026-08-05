# ADR 0014: Represent Workflows as Durable Specifications

- Status: Accepted
- Date: 2026-08-04

## Context

Azathoth optimizes AI behavior by generating, executing, and evaluating candidate strategies.

As optimization expands beyond individual prompt strategies, the system requires a durable representation of complete workflows.

A workflow must describe *what* work should be performed without embedding runtime concerns such as language model implementations, tool instances, or execution state.

Future workflows may contain heterogeneous steps including:

- prompt-based reasoning
- tool invocation
- retrieval
- deterministic computation
- conditional routing
- human review

Different workflow steps may require different language models, different tools, and different execution policies.

## Decision

Workflows are represented as immutable specifications.

A workflow consists of:

- workflow metadata
- an ordered collection of workflow step specifications

Each workflow step owns its own executable specification.

Initially, workflow steps contain prompt strategy specifications.

Future step types will be introduced without changing the overall workflow representation.

Model requirements remain step-scoped rather than workflow-scoped.

Workflow specifications intentionally contain no runtime execution dependencies.

## Consequences

### Positive

- Workflows are durable, serializable configuration.
- Workflow definitions remain independent of runtime providers.
- Individual steps can evolve independently.
- Different workflow steps may use different language models.
- Future tool, retrieval, and routing steps can be introduced without redesigning the workflow model.
- Workflow specifications can be generated, versioned, optimized, and replayed.

### Negative

- Workflow specifications describe structure only and cannot yet be executed.

## Alternatives Considered

### Bind one language model to an entire workflow

Rejected because different workflow steps frequently benefit from different models, tools, and execution policies.

### Couple workflow specifications to executable implementations

Rejected because durable specifications should remain independent of runtime dependencies and provider implementations.