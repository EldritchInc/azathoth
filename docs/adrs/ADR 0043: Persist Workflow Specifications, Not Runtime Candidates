# ADR 0043: Persist Workflow Specifications, Not Runtime Candidates

- Status: Accepted
- Date: 2026-08-18

## Context

Azathoth separates model-independent workflow descriptions from executable
runtime candidates.

`WorkflowSpecification` describes the durable structure and requirements of a
workflow without containing resolved runtime dependencies.

`WorkflowCandidate` contains executable strategies produced by resolving those
requirements against configured runtime infrastructure.

```text
WorkflowSpecification
        │
        ▼
Candidate Generation
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
```

Applications need workflows to survive process restarts without requiring those
workflows to be embedded in application source code.

Persisting executable workflow candidates would also persist runtime concerns
such as resolved language model and tool implementations.

Those runtime objects may depend on:

- configured providers;
- credentials;
- local runtime state;
- executable tool implementations; and
- other environment-specific infrastructure.

The durable workflow representation should remain independent from those
concerns.

## Decision

Azathoth persists `WorkflowSpecification`.

It does not persist `WorkflowCandidate`.

```text
Durable
────────────────────────────
WorkflowSpecification
        │
        ▼
WorkflowRepository
        │
        ▼
Persistent Storage

Runtime
────────────────────────────
WorkflowSpecification
        │
        ▼
Candidate Generation
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
```

A persisted workflow therefore records what the workflow requires, not the
runtime implementations that happened to satisfy those requirements during a
particular process execution.

## Repository Boundary

`WorkflowRepository` defines the storage-neutral persistence contract for
workflow specifications.

Current implementations include:

```text
WorkflowRepository
        │
        ├── InMemoryWorkflowRepository
        │
        └── SQLiteWorkflowRepository
```

Repositories support:

- saving workflow specifications;
- retrieving a specification by workflow identifier; and
- enumerating persisted specifications in deterministic insertion order.

Workflow identifiers are unique within a repository.

Saving another workflow with an existing identifier is rejected rather than
silently replacing the existing specification.

## SQLite Representation

`SQLiteWorkflowRepository` persists each workflow specification as its
serialized model representation.

```text
WorkflowSpecification
        │
        ▼
model_dump_json()
        │
        ▼
SQLite
        │
        ▼
model_validate_json()
        │
        ▼
WorkflowSpecification
```

Deserialization reconstructs the normal workflow domain model.

The reconstructed specification therefore passes through the same model
validation as a directly constructed specification.

This includes validation of:

- unique step identifiers;
- dependency references;
- dependency cycles;
- input bindings;
- output bindings;
- condition references; and
- upstream value relationships.

SQLite is a persistence implementation detail.

Higher-level workflow components do not depend on SQLite.

## Workflow Catalogs

Repository state is exposed to higher-level systems through an immutable
`WorkflowCatalog`.

`WorkflowCatalogLoader` performs the repository-to-catalog transition.

```text
Persistent Storage
        │
        ▼
WorkflowRepository
        │
        ▼
WorkflowCatalogLoader
        │
        ▼
WorkflowCatalog
        │
        ▼
WorkflowSpecification
```

The catalog:

- preserves repository order;
- exposes workflow identifiers in deterministic order;
- supports exact lookup by workflow identifier;
- supports lookup by workflow name; and
- rejects duplicate workflow identifiers.

The catalog is an immutable snapshot of repository state.

It does not query persistence during lookup.

## Candidate Generation

Persistence remains below candidate generation.

```text
SQLite
  │
  ▼
SQLiteWorkflowRepository
  │
  ▼
WorkflowCatalogLoader
  │
  ▼
WorkflowCatalog
  │
  ▼
WorkflowSpecification
  │
  ▼
generate_workflow_candidate()
  │
  ▼
WorkflowCandidate
```

Candidate generation receives an ordinary `WorkflowSpecification`.

It does not know whether that specification originated from:

- direct application construction;
- an in-memory repository;
- SQLite; or
- another future repository implementation.

Runtime model and tool implementations are resolved only when the durable
specification becomes an executable candidate.

## Persisted Tool Requirements

Persisted workflows may contain tool-backed steps.

A tool-backed workflow step persists its durable `ToolRequirement`, not a
resolved `ToolImplementation`.

```text
Persisted WorkflowSpecification
        │
        ▼
ToolStepSpecification
        │
        ▼
ToolRequirement

            process/runtime boundary

ToolRequirement
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

This preserves the existing distinction between durable capability requirements
and executable tool implementations.

A workflow and its required tool artifacts may therefore be persisted
independently and reconstructed before candidate generation.

## Reconstructed Execution

A reconstructed workflow follows the same execution path as a directly
constructed workflow.

```text
Persisted Workflow
        +
Persisted Tool
        │
        ▼
Repository Reconstruction
        │
        ▼
Immutable Catalogs
        │
        ▼
Candidate Generation
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
```

Workflow persistence introduces no separate execution path.

A reconstructed workflow retains its:

- metadata;
- prompt-backed step specifications;
- tool-backed step specifications;
- dependencies;
- input bindings;
- output bindings;
- conditions;
- retry policies; and
- failure policies.

Tool-backed steps can resolve persisted tool implementations, consume upstream
workflow values, produce structured workflow values, and participate in normal
conditional routing after reconstruction.

## Consequences

### Positive

- Workflow definitions can survive process restarts.
- Workflows do not need to be embedded in application source code.
- Durable workflow configuration remains independent from runtime objects.
- Persisted specifications continue to receive normal domain validation.
- Repository implementations remain replaceable.
- Higher-level systems operate against immutable workflow catalogs.
- Candidate generation remains storage-neutral.
- Runtime provider and tool implementations are resolved when needed.
- Persisted workflows use the same execution path as directly constructed
  workflows.

### Negative

- Executing a persisted workflow still requires compatible runtime
  infrastructure.
- A persisted tool requirement does not guarantee that an executable tool
  implementation will be available later.
- A persisted model requirement does not guarantee that a compatible language
  model will be configured later.
- SQLite currently stores the workflow specification as a serialized model
  payload rather than as normalized relational workflow tables.
- Changing durable model schemas may eventually require explicit persistence
  migration policy.

## Alternatives Considered

### Persist WorkflowCandidate

Rejected.

A `WorkflowCandidate` contains resolved executable strategies and therefore
crosses the boundary between durable configuration and runtime infrastructure.

Persisting candidates would couple durable workflow state to the runtime
environment in which candidate generation occurred.

### Persist Resolved Model Implementations

Rejected.

Workflow specifications declare model requirements.

Executable language models belong to provider/runtime configuration and are
resolved when candidates are generated.

### Persist Resolved Tool Implementations Inside Workflows

Rejected.

Tool implementations already have their own durability and resolution
boundaries.

Workflow specifications persist `ToolRequirement` and allow the tool subsystem
to resolve an executable implementation independently.

### Make Candidate Generation Read Directly From SQLite

Rejected.

Candidate generation should operate on workflow domain objects, not persistence
technology.

`WorkflowRepository`, `WorkflowCatalogLoader`, and `WorkflowCatalog` isolate
storage from candidate generation.

### Store Workflows Only as Application Configuration

Rejected.

Application-only configuration would require workflow definitions to remain
embedded in or deployed alongside application source.

A repository allows workflow specifications to become independently durable
domain artifacts.

## Result

Azathoth now has a durable boundary for workflow definitions.

```text
             DURABLE
                │
                ▼
      WorkflowSpecification
                │
                ▼
       WorkflowRepository
                │
                ▼
        Persistent Storage
                │
          process restart
                │
                ▼
       WorkflowRepository
                │
                ▼
     WorkflowCatalogLoader
                │
                ▼
        WorkflowCatalog
                │
                ▼
      WorkflowSpecification
                │
                ▼
          RUNTIME BOUNDARY
                │
                ▼
       Candidate Generation
          /             \
         ▼               ▼
Model Resolution    Tool Resolution
         \               /
          \             /
           ▼           ▼
         WorkflowCandidate
                │
                ▼
          WorkflowRunner
```

Persistence records the durable workflow recipe.

Runtime candidate generation determines how that recipe becomes executable in
the current environment.

No workflow optimization policy is introduced by workflow persistence.