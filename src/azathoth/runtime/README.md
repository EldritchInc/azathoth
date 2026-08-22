# Runtime

`azathoth.runtime` provides the process-local composition boundary between
Azathoth's durable declarative configuration and executable workflow
candidates.

## Purpose

Azathoth deliberately separates durable artifacts from runtime implementations.

```text
DURABLE

WorkflowSpecification
ModelMetadata
ToolDefinition
ToolImplementation
```

```text
PROCESS-LOCAL

LanguageModelRegistry
ToolResolver
ToolImplementationResolver
WorkflowCandidate
```

`AzathothRuntime` brings the configuration required for candidate generation
into one supported application-facing object.

## AzathothRuntime

A runtime contains:

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

The workflow, model, and language-model dependencies are required.

Tool configuration is optional and defaults to empty immutable catalogs.

```python
from azathoth.runtime import AzathothRuntime

runtime = AzathothRuntime(
    workflows=workflow_catalog,
    models=model_catalog,
    language_models=language_model_registry,
)
```

A runtime with tool-backed workflows may additionally provide:

```python
runtime = AzathothRuntime(
    workflows=workflow_catalog,
    models=model_catalog,
    language_models=language_model_registry,
    tools=tool_catalog,
    tool_implementations=tool_implementation_catalog,
)
```

## Candidate Generation

Configured workflows become executable by stable workflow identity.

```python
candidate = runtime.generate_workflow_candidate(
    workflow_id,
)
```

The runtime performs:

```text
workflow ID
    │
    ▼
WorkflowCatalog
    │
    ▼
WorkflowSpecification
    │
    +
ModelCatalog
LanguageModelRegistry
ToolResolver
ToolImplementationResolver
    │
    ▼
existing workflow candidate generation
    │
    ▼
WorkflowCandidate
```

Candidate generation remains owned by the workflow subsystem.

`AzathothRuntime` delegates to that existing implementation.

## Unknown Workflows

Requesting an identifier absent from the configured workflow catalog raises:

```text
WorkflowNotConfiguredError
```

This distinguishes runtime configuration failure from failures that occur while
turning an existing workflow specification into an executable candidate.

## Prompt-Backed Steps

Prompt-backed workflow steps continue to resolve through the provider
subsystem.

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

The runtime introduces no model-selection policy.

## Tool-Backed Steps

Tool-backed workflow steps continue to resolve through the tool subsystem.

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

The runtime constructs and retains the resolvers required by this existing
path.

## RuntimeEnvironment

`RuntimeEnvironment` describes the application-facing runtime surface.

Consumers that need runtime composition can depend on the protocol rather than
the concrete implementation.

The protocol exposes:

- configured workflow catalogs;
- configured model catalogs;
- executable language-model implementations;
- configured tools;
- configured tool implementations;
- tool resolvers; and
- workflow candidate generation.

## Persistence and Reconstruction

The runtime does not load repositories.

Durable state is reconstructed first.

```text
repository
    │
    ▼
catalog loader
    │
    ▼
catalog
```

Those catalogs are then supplied to `AzathothRuntime`.

```text
WorkflowCatalog
ModelCatalog
ToolCatalog
ToolImplementationCatalog
        +
LanguageModelRegistry
        │
        ▼
AzathothRuntime
```

This keeps persistence independent from runtime assembly.

## Reconstructed Execution

A persisted application can rebuild its declarative configuration after process
restart and execute through the same workflow path.

```text
SQLite repositories
        │
        ▼
catalog loaders
        │
        ▼
reconstructed catalogs
        │
        +
process-local LanguageModelRegistry
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
```

There is no separate execution path for persisted configuration.

## Boundaries

`azathoth.runtime` intentionally does not own:

- repository construction;
- database lifecycle;
- workflow execution;
- benchmark execution;
- scoring;
- ranking;
- experiments;
- optimization;
- provider credential persistence; or
- arbitrary application services.

It is a composition boundary, not an application framework.

## Complete Runtime Flow

```text
                DURABLE WORLD

WorkflowRepository
        │
        ▼
WorkflowCatalog
        │

ModelRepository
        │
        ▼
ModelCatalog
        │

ToolRepository
        │
        ├──► ToolCatalog
        └──► ToolImplementationCatalog
        │
        │
        │           PROCESS LOCAL
        │
        │       LanguageModelRegistry
        │                │
        └────────┬───────┘
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