# ADR 0052: Introduce a Process-Local Runtime Composition Boundary

- Status: Accepted
- Date: 2026-08-22

## Context

Azathoth separates durable declarative configuration from executable
process-local runtime dependencies.

Durable artifacts include:

```text
WorkflowSpecification
ModelMetadata
ToolDefinition
ToolImplementation
```

Those artifacts may be persisted and reconstructed independently.

Executable runtime dependencies include:

```text
LanguageModelRegistry
ToolResolver
ToolImplementationResolver
```

Before this decision, applications that wanted to execute reconstructed
workflows had to manually assemble those pieces before calling workflow
candidate generation.

```text
WorkflowCatalog
ModelCatalog
LanguageModelRegistry
ToolCatalog
ToolImplementationCatalog
        │
        ▼
manual resolver construction
        │
        ▼
generate_workflow_candidate(...)
```

That assembly was valid but required every consumer to understand Azathoth's
internal runtime dependency graph.

As the project approaches a CLI and other application-facing interfaces, that
composition should have one supported process-local boundary.

## Decision

Azathoth introduces `AzathothRuntime`.

```text
AzathothRuntime
├── WorkflowCatalog
├── ModelCatalog
├── LanguageModelRegistry
├── ToolCatalog
├── ToolImplementationCatalog
├── ToolResolver
└── ToolImplementationResolver
```

`AzathothRuntime` composes already-constructed catalogs and runtime
implementations.

It does not load repositories itself.

It does not persist runtime state.

It does not replace workflow candidate generation.

## Required Runtime Inputs

A runtime requires:

```text
WorkflowCatalog
ModelCatalog
LanguageModelRegistry
```

These are required because a runtime must know:

- which workflows are configured;
- which models are configured; and
- which model implementations can execute.

Tool configuration is optional.

```text
ToolCatalog
ToolImplementationCatalog
```

When omitted, empty immutable catalogs are used.

This allows prompt-only applications to construct a runtime without artificial
tool configuration.

## Runtime-Owned Resolvers

The runtime constructs and retains:

```text
ToolResolver
ToolImplementationResolver
```

from its configured tool catalogs.

```text
ToolCatalog
     │
     ▼
ToolResolver

ToolImplementationCatalog
     │
     ▼
ToolImplementationResolver
```

Resolver instances are process-local runtime objects.

They are created once during runtime construction and reused.

## Candidate Generation

`AzathothRuntime` exposes workflow candidate generation by durable workflow
identity.

```python
candidate = runtime.generate_workflow_candidate(
    workflow_id,
)
```

The runtime first resolves the workflow specification from its configured
`WorkflowCatalog`.

```text
workflow ID
    │
    ▼
WorkflowCatalog
    │
    ▼
WorkflowSpecification
```

If the workflow is not configured, the runtime raises
`WorkflowNotConfiguredError`.

The runtime then delegates to the existing workflow candidate-generation
function.

```text
WorkflowSpecification
        +
ModelCatalog
        +
LanguageModelRegistry
        +
ToolResolver
        +
ToolImplementationResolver
        │
        ▼
generate_workflow_candidate(...)
        │
        ▼
WorkflowCandidate
```

No second candidate-generation implementation is introduced.

## Existing Generation Semantics Remain Authoritative

Prompt-backed workflow steps continue to resolve through:

```text
PromptStrategySpec
        │
        ▼
ModelCatalog
        +
LanguageModelRegistry
        │
        ▼
PromptStrategy
```

Tool-backed steps continue to resolve through:

```text
ToolStepSpecification
        │
        ▼
ToolResolver
        │
        ▼
ToolDefinition
        │
        ▼
ToolImplementationResolver
        │
        ▼
ToolImplementation
        │
        ▼
ToolStrategy
```

The runtime does not change either resolution algorithm.

Errors from existing workflow generation continue to propagate normally.

## Runtime Environment Protocol

`RuntimeEnvironment` describes the public runtime composition surface.

It exposes:

```text
workflow catalog
model catalog
language-model registry
tool catalog
tool implementation catalog
tool resolver
tool implementation resolver
candidate generation
```

Application-facing consumers may therefore depend on the runtime protocol
rather than the concrete `AzathothRuntime` implementation.

This keeps future interfaces such as a CLI from depending directly on runtime
construction internals.

## Relationship to Persistence

Runtime composition sits above persistence reconstruction.

```text
Repositories
    │
    ▼
Catalog Loaders
    │
    ▼
Immutable Catalogs
    │
    ▼
AzathothRuntime
```

The runtime does not know whether a catalog originated from:

- SQLite;
- memory;
- application configuration;
- another storage implementation; or
- another future source.

Persistence policy remains outside the runtime.

## Reconstructed Runtime Execution

A complete runtime may be reconstructed after process restart.

```text
PERSISTED

WorkflowSpecification
      │
      ▼
SQLiteWorkflowRepository

ModelMetadata
      │
      ▼
SQLiteModelRepository

ToolDefinition
ToolImplementation
      │
      ▼
SQLiteToolRepository
```

After restart:

```text
SQLiteWorkflowRepository
        │
        ▼
WorkflowCatalogLoader
        │
        ▼
WorkflowCatalog

SQLiteModelRepository
        │
        ▼
ModelCatalogLoader
        │
        ▼
ModelCatalog

SQLiteToolRepository
        │
        ▼
ToolCatalogLoader
        │
        ├── ToolCatalog
        └── ToolImplementationCatalog
```

Process-local implementations are then attached.

```text
LanguageModelRegistry
```

The reconstructed state is composed into:

```text
AzathothRuntime
```

which can generate an executable workflow candidate by workflow identifier.

```text
AzathothRuntime
      │
      ▼
generate_workflow_candidate(workflow_id)
      │
      ▼
WorkflowCandidate
      │
      ▼
WorkflowRunner
```

The resulting workflow executes through the same runtime path as a workflow
constructed directly in application code.

## Process-Local Runtime State

`AzathothRuntime` itself is not durable state.

Two runtimes reconstructed from the same durable catalogs are separate
process-local objects.

```text
durable catalogs
     │
     ├──────────► runtime A
     │
     └──────────► runtime B
```

Their reconstructed declarative configuration may be equal.

Their process-local registries and resolver instances remain independent.

## Runtime Is Not Execution

`AzathothRuntime` composes the dependencies required to produce executable
workflow candidates.

It does not replace `WorkflowRunner`.

```text
AzathothRuntime
      │
      ▼
WorkflowCandidate
      │
      ▼
WorkflowRunner
```

Workflow execution policy remains in the workflow subsystem.

## Runtime Is Not Optimization

The runtime does not:

- score workflows;
- rank workflows;
- run experiments;
- mutate candidates;
- select models;
- choose tools; or
- optimize workflows.

Optimization remains behind the `WorkflowOptimizer` boundary.

The runtime merely provides the executable environment required by candidate
generation.

## Runtime Is Not Persistence

The runtime does not:

- open databases;
- load repositories;
- persist workflows;
- persist models;
- persist tools; or
- own storage lifecycle.

Applications remain responsible for constructing or reconstructing catalogs
before runtime composition.

## Runtime Is Not a Service Locator

The runtime exposes a deliberately narrow dependency surface.

It is not intended to become a registry for arbitrary application services.

New responsibilities should be added only when they are required to compose
Azathoth's core execution dependencies.

## Consequences

### Positive

- Applications have one supported runtime composition boundary.
- Workflow candidate generation can be invoked by stable workflow identity.
- Prompt-only runtimes require no artificial tool configuration.
- Tool resolvers are constructed consistently.
- Existing candidate-generation behavior remains authoritative.
- Persistence remains independent from runtime composition.
- CLI and future application interfaces can depend on a small runtime surface.
- Reconstructed durable configuration can be executed without every consumer
  manually rebuilding Azathoth's dependency graph.

### Negative

- Applications must still reconstruct catalogs before constructing a runtime.
- Provider-specific executable implementations must still be attached
  process-locally.
- Runtime construction now represents a public application-facing abstraction
  that must remain intentionally narrow.
- The runtime does not currently provide higher-level execution, benchmark, or
  optimization convenience methods.

## Alternatives Considered

### Let Every Consumer Assemble Runtime Dependencies Manually

Rejected as the primary application-facing path.

Manual composition remains possible, but requiring every CLI or application to
reconstruct the same dependency graph would duplicate architecture outside the
core library.

### Make the CLI the Composition Root

Rejected.

That would embed reusable application architecture inside command handlers and
make non-CLI consumers reconstruct the same logic separately.

### Let AzathothRuntime Open Repositories

Rejected.

Persistence sources and runtime execution have different responsibilities.

The runtime should consume reconstructed catalogs rather than own storage
policy.

### Add Workflow Execution Directly to AzathothRuntime

Rejected for this decision.

`WorkflowRunner` already owns workflow execution behavior.

Runtime composition should not duplicate or absorb that responsibility.

### Persist AzathothRuntime

Rejected.

The runtime contains process-local executable dependencies.

Durable state belongs in the existing repository and catalog boundaries.

## Result

Azathoth now has one process-local ignition point for reconstructed
configuration.

```text
durable configuration
        +
runtime implementations
        │
        ▼
AzathothRuntime
        │
        ▼
workflow ID
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
```

Persistence reconstructs the world.

Runtime composition makes it executable.

Workflow execution runs it.