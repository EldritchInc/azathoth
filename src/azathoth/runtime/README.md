# Runtime

`azathoth.runtime` defines the process-local composition boundary that turns
Azathoth's reconstructed durable state and executable implementations into one
coherent runtime environment.

The runtime is deliberately small.

It does not own persistence, workflow execution, optimization, provider
discovery, promotion, or production invocation.

It composes the dependencies those systems require.

```text
                 DURABLE / RECONSTRUCTED

WorkflowCatalog          WorkflowProductionState
       │                           │
ModelCatalog             ModelPortfolio
       │                           │
ToolCatalog              ToolImplementationCatalog
       │                           │
       └─────────────┬─────────────┘
                     │
                     │      PROCESS-LOCAL
                     │
                     ├──── LanguageModelRegistry
                     │
                     ▼
              AzathothRuntime
                     │
                     ▼
              runtime operations
```

`AzathothRuntime` is therefore a composition boundary rather than a durable
domain object or application framework.

## Why a Runtime Exists

Azathoth deliberately separates durable declarative state from executable
process-local implementations.

Durable or reconstructed state can describe:

```text
WorkflowCatalog
ModelCatalog
ModelPortfolio
WorkflowProductionState
ToolCatalog
ToolImplementationCatalog
```

Executable process-local state includes:

```text
LanguageModelRegistry
ToolResolver
ToolImplementationResolver
```

Neither side alone is sufficient for execution.

A workflow specification can describe model or tool requirements without
containing live provider clients or process-local resolver instances.

Likewise, a provider client has no authority to decide which durable workflow,
model policy, or production state should use it.

`AzathothRuntime` brings these worlds together without collapsing their
boundaries.

## AzathothRuntime

`AzathothRuntime` is the concrete V1 runtime composition object.

It is constructed from:

```text
AzathothRuntime
├── WorkflowCatalog
├── ModelCatalog
├── ModelPortfolio
├── LanguageModelRegistry
├── WorkflowProductionState*
├── ToolCatalog
├── ToolImplementationCatalog
├── ToolResolver
└── ToolImplementationResolver
```

The runtime receives:

- configured workflow specifications
- normalized current model metadata
- organizational model-selection authorization
- executable language-model implementations
- current production workflow state
- durable tool definitions
- durable tool implementations

It constructs the process-local tool resolvers required for candidate
generation.

Tool catalogs are optional and default to empty immutable catalogs.

Production states are optional and default to an empty tuple.

## Runtime Is a Snapshot

An `AzathothRuntime` represents one process-local composition of state.

It is not a live view over repositories.

```text
durable state
     │
     ▼
reconstruction
     │
     ▼
runtime A
```

If durable state later changes, an already constructed runtime does not
silently mutate to reflect that change.

A new runtime can be reconstructed:

```text
durable state A
     │
     ▼
runtime A

durable state B
     │
     ▼
runtime B
```

This property is important for deterministic execution.

Process-local runtime behavior depends on the state that was explicitly
composed into that runtime.

## Configured Workflows

The runtime exposes configured workflows through its `WorkflowCatalog`.

```text
runtime.workflows
       │
       ▼
WorkflowCatalog
       │
       ▼
WorkflowSpecification
```

Workflow specifications remain durable workflow intent.

The runtime does not modify them during candidate generation or execution.

## Current Model Metadata

The runtime exposes normalized model metadata through its `ModelCatalog`.

```text
runtime.models
      │
      ▼
ModelCatalog
```

The catalog describes the model universe composed into this runtime.

It is metadata, not executable provider state.

Executable language-model implementations remain separate.

## Organizational Model Authorization

The runtime exposes the organization's `ModelPortfolio`.

```text
runtime.portfolio
       │
       ▼
ModelPortfolio
```

The portfolio describes models authorized for general Azathoth selection.

This is distinct from the current model catalog:

```text
ModelCatalog
    what models are represented as available

ModelPortfolio
    what models the organization authorizes Azathoth to select
```

Candidate generation can therefore consider both availability and
authorization without embedding organizational policy into provider clients or
workflow execution machinery.

## Executable Language Models

The runtime exposes process-local executable models through
`LanguageModelRegistry`.

```text
runtime.language_models
        │
        ▼
LanguageModelRegistry
        │
        ▼
LanguageModel
```

The registry contains executable implementations.

It is distinct from `ModelCatalog`.

```text
ModelCatalog
    model metadata

LanguageModelRegistry
    executable model implementations
```

A model represented in metadata is not necessarily executable in every runtime
process.

## Tool Configuration

The runtime exposes both durable tool capability and durable implementation
configuration.

```text
runtime.tools
       │
       ▼
ToolCatalog

runtime.tool_implementations
       │
       ▼
ToolImplementationCatalog
```

These catalogs remain separate because durable tool capability and executable
implementation identity are different concerns.

## Tool Resolvers

`AzathothRuntime` constructs and retains:

- `ToolResolver`
- `ToolImplementationResolver`

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

These resolver instances are process-local runtime objects.

They provide the existing tool-resolution boundaries required by workflow
candidate generation.

## Candidate Generation

The runtime exposes candidate generation by durable workflow identity.

```python
candidate = runtime.generate_workflow_candidate(
    workflow_id,
)
```

The runtime first resolves the configured workflow specification.

```text
workflow ID
    │
    ▼
WorkflowCatalog
    │
    ▼
WorkflowSpecification
```

If the workflow is absent, candidate generation fails explicitly with
`WorkflowNotConfiguredError`.

For a configured workflow, the runtime delegates to the workflow subsystem's
existing `generate_workflow_candidate` implementation.

```text
WorkflowSpecification
        +
ModelCatalog
        +
ModelPortfolio
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

The runtime does not implement a second candidate-generation algorithm.

Workflow candidate-generation semantics remain owned by
`azathoth.workflows`.

## Prompt-Backed Candidate Generation

Prompt-backed workflow steps resolve through the existing provider and
prompting boundaries.

Conceptually:

```text
PromptStrategySpec
        │
        ├── model selection intent
        │
        ▼
ModelCatalog
        +
ModelPortfolio
        +
LanguageModelRegistry
        │
        ▼
PromptStrategy
```

The runtime supplies the environment.

It does not independently invent model-selection policy.

## Tool-Backed Candidate Generation

Tool-backed workflow steps resolve through the existing tool boundaries.

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

Again, the runtime supplies the composed environment.

The tool subsystem owns tool-resolution semantics.

## Production State

The runtime may contain current `WorkflowProductionState` values.

```text
runtime.production_states
        │
        ▼
WorkflowProductionState*
```

Each production workflow identity may appear at most once.

Runtime construction rejects duplicate production states for the same workflow.

The active production state for one workflow can be resolved with:

```python
state = runtime.production_state(
    workflow_id,
)
```

The result is either:

```text
WorkflowProductionState
```

or:

```text
None
```

when that workflow has no production state in this runtime.

## Production State Is Execution Authority

The runtime's production-state surface preserves the production ontology
defined by `azathoth.workflows`.

```text
WorkflowProductionState
    current durable production intent
    execution authority

WorkflowProductionRevision
    immutable deployment history
    audit evidence
```

The runtime contains production states.

It does not need production revisions to determine current production behavior.

```text
production repository
        │
        ▼
current WorkflowProductionState
        │
        ▼
runtime reconstruction
        │
        ▼
AzathothRuntime
        │
        ▼
runtime.production_state(workflow_id)
```

Historical revision ordering is therefore not used to infer current production
authority.

There is no runtime concept of:

```text
latest revision = active
```

and no active revision pointer is required.

## Runtime Production State Is Still a Snapshot

Although `WorkflowProductionState` is durable production execution authority,
the `AzathothRuntime` object containing it remains process-local.

Suppose a runtime is reconstructed with production state A:

```text
durable ACTIVE = state A
        │
        ▼
runtime A
        │
        ▼
production state A
```

If durable production state is later replaced with state B, the already
constructed runtime remains unchanged.

```text
runtime A ─────► state A

durable ACTIVE = state B
        │
        ▼
runtime B ─────► state B
```

This prevents an existing runtime object from changing behavior through hidden
repository reads.

Applications that require newly persisted production intent reconstruct a new
runtime.

## RuntimeEnvironment

`RuntimeEnvironment` defines the application-facing protocol for runtime
composition.

It exposes the runtime dependencies and operations required by higher-level
application services.

The protocol includes access to:

```text
WorkflowCatalog
ModelCatalog
ModelPortfolio
LanguageModelRegistry
ToolCatalog
ToolImplementationCatalog
ToolResolver
ToolImplementationResolver
```

and executable candidate generation:

```text
generate_workflow_candidate(workflow_id)
```

Application services can therefore depend on the runtime abstraction rather
than on concrete runtime construction details.

This is especially useful for CLI application services that need runtime
capabilities without owning runtime assembly.

## Persistence and Reconstruction

`AzathothRuntime` does not construct repositories.

Persistence is resolved before runtime composition.

```text
repository
    │
    ▼
loader / reconstruction
    │
    ▼
durable domain state
    │
    ▼
AzathothRuntime
```

Examples include:

```text
WorkflowRepository
        │
        ▼
WorkflowCatalogLoader
        │
        ▼
WorkflowCatalog

ModelRepository
        │
        ▼
ModelCatalogLoader
        │
        ▼
ModelCatalog

ModelPortfolioRepository
        │
        ▼
ModelPortfolioLoader
        │
        ▼
ModelPortfolio

WorkflowProductionStateRepository
        │
        ▼
WorkflowProductionState*
```

The resulting state is supplied to the runtime explicitly.

The runtime does not know or care whether that state originated from SQLite,
memory, application configuration, or another persistence implementation.

## CLI Runtime Bootstrap

The command-line application provides an application-level bootstrap boundary
for reconstructing runtime state.

```text
CliRuntimeConfiguration
        │
        ▼
load_runtime()
        │
        ├── reconstruct durable state
        ├── discover / compose current model state
        ├── reconstruct authorization
        ├── reconstruct production state
        └── attach executable implementations
        │
        ▼
AzathothRuntime
```

Environment variables, database selection, provider credentials, and
application persistence wiring remain CLI concerns.

`AzathothRuntime` itself does not read environment variables or decide which
repositories an application should construct.

## Reconstructed Execution

Persisted configuration and directly constructed configuration use the same
candidate-generation path.

```text
persistent repositories
        │
        ▼
reconstructed domain state
        │
        +
process-local implementations
        │
        ▼
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
        │
        ▼
WorkflowRun
```

There is no special execution implementation for reconstructed workflows.

Persistence changes where configuration comes from, not how candidates
execute.

## Runtime Is Not Workflow Execution

`AzathothRuntime` produces executable candidates.

It does not execute them.

```text
AzathothRuntime
       │
       ▼
WorkflowCandidate
       │
       ▼
WorkflowRunner
       │
       ▼
WorkflowRun
```

`WorkflowRunner` remains the execution boundary.

This keeps composition separate from empirical execution evidence.

## Runtime Is Not Optimization

The runtime does not:

- score workflow runs
- rank candidates
- run experiments
- mutate candidates
- select empirical winners
- promote workflows
- optimize workflows

Optimization remains behind the optimization and workflow experimentation
boundaries.

The runtime supplies an executable environment that those systems may use.

It does not own their policy.

## Runtime Is Not Production Invocation

The runtime exposes the current production state required for production
execution.

It does not itself create or persist production invocations.

Production invocation remains an application/domain service using the runtime
environment and production persistence boundaries.

Conceptually:

```text
AzathothRuntime
       │
       ├── current production state
       ├── model catalog
       ├── executable model registry
       └── tool resolvers
       │
       ▼
production invocation service
       │
       ▼
ProductionInvocation
       +
WorkflowRun
```

This prevents the runtime from becoming a catch-all production service.

## Runtime Is Not Promotion

Promotion changes durable production intent.

Runtime composition does not.

```text
WorkflowCandidate
       │
       ▼
promotion
       │
       ▼
WorkflowProductionState
       │
       ▼
persistent production repository
```

A subsequently reconstructed runtime can contain that new production state.

The runtime itself does not perform the promotion merely because a candidate
exists.

## Runtime Is Not Persistence

The runtime does not:

- open databases
- construct repositories
- save workflow specifications
- save model metadata
- save model portfolios
- save production state
- save production revisions
- save workflow runs
- save production invocations
- own storage lifecycle

Those responsibilities remain behind explicit persistence and
application-composition boundaries.

## Runtime Is Not Provider Discovery

Provider discovery determines current external provider truth.

Runtime composition consumes the resulting model state.

```text
provider
    │
    ▼
ProviderModelDirectory
    │
    ▼
ProviderModelCatalogSynchronizer
    │
    ▼
ModelCatalog
    │
    ▼
AzathothRuntime
```

The runtime does not poll providers or infer external model changes after
construction.

## Runtime Is Not a Service Locator

`AzathothRuntime` intentionally exposes only the dependencies required for
supported Azathoth runtime behavior.

It is not a general registry for arbitrary application services.

New application functionality should not automatically become another runtime
property.

A dependency belongs in runtime composition only when it forms part of the
shared executable environment required by runtime operations.

## Runtime Errors

Runtime-specific failures derive from `AzathothRuntimeError`.

V1 exposes:

```text
AzathothRuntimeError
└── WorkflowNotConfiguredError
```

`WorkflowNotConfiguredError` distinguishes the absence of a configured workflow
from failures that occur while resolving an existing specification into an
executable candidate.

Errors owned by workflow generation, providers, tools, execution, or other
subsystems continue to propagate through their respective boundaries.

## Architectural Boundaries

The V1 runtime architecture deliberately preserves these distinctions:

```text
durable configuration
    ≠ process-local runtime

ModelCatalog
    ≠ LanguageModelRegistry

ModelPortfolio
    ≠ ModelCatalog

WorkflowSpecification
    ≠ WorkflowCandidate

WorkflowProductionState
    ≠ WorkflowProductionRevision

AzathothRuntime
    ≠ WorkflowRunner

AzathothRuntime
    ≠ optimizer

AzathothRuntime
    ≠ persistence layer

AzathothRuntime
    ≠ provider discovery

AzathothRuntime
    ≠ production invocation service
```

The runtime has one central responsibility:

```text
reconstructed durable state
        +
process-local executable implementations
        │
        ▼
one coherent execution environment
```

Keeping that responsibility narrow allows persistence, providers, workflows,
optimization, production operations, and application interfaces to evolve
without turning runtime composition into hidden policy.