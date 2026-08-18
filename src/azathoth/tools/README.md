# Tools

The `azathoth.tools` package models durable capabilities, executable
implementations, deterministic execution, verification, and implementation
resolution.

```text
                            ToolRequirements
                     │
                     ▼
              ToolRequirement
                     │
                     ▼
                ToolResolver
                     │
                     ▼
               ToolDefinition
                     │
                     ▼
             ToolRepository
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
 ToolCatalogLoader    ToolImplementationResolver
         │                       │
         ▼                       ▼
  ToolCatalog      ToolImplementationCatalog
                                 │
                                 ▼
                      ToolImplementation
                         /            \
                        ▼              ▼
                ToolExecutor     ToolTestCase
                        │              │
                        ▼              │
              PythonToolExecutor      │
                        │              │
                        └──────┬───────┘
                               ▼
                         ToolVerifier
                               │
                               ▼
                       ToolVerification
```

## Capability Resolution

Capability resolution maps durable capability requirements to matching tool
definitions.

Resolution depends only on capability identity and version.

## Implementation Resolution

Implementation resolution maps capability definitions to executable tool
implementations.

Runtime constraints are evaluated during implementation resolution.

Implementation resolution introduces no optimization or ranking policy.

## Persistence

Tool definitions, implementations, and deterministic test cases may be stored
outside the Azathoth source tree.

`ToolRepository` provides a storage-neutral persistence boundary.

Current repository implementations include:

- in-memory persistence; and
- SQLite persistence.

Repositories reconstruct immutable tool catalogs used by the existing
resolution and execution infrastructure.

Persistence remains independent of capability resolution, implementation
selection, execution, and verification.

## Tool Execution

Tool executors execute deterministic implementations using structured inputs
and structured outputs.

Execution remains independent of capability discovery and implementation
selection.

## ToolStrategy

`ToolStrategy` adapts a resolved durable tool implementation to Azathoth's
common `Strategy` protocol.

```text
ToolImplementation
        +
ToolExecutor
        │
        ▼
   ToolStrategy
        │
        ▼
     Strategy
```

A tool strategy:

- exposes stable strategy metadata;
- retains the resolved `ToolImplementation`;
- receives normal Azathoth `Context`;
- extracts workflow-bound structured inputs when present;
- delegates execution to `ToolExecutor`; and
- returns structured output through `StrategyOutcome`.

Tool strategies do not implement workflow orchestration.

Retries, failure policies, dependency ordering, value propagation, and
conditional execution remain responsibilities of the workflow package.

## Tools in Workflows

Workflow specifications can declare durable tool requirements using
`ToolStepSpecification`.

```text
WorkflowStepSpecification
        │
        ▼
ToolStepSpecification
        │
        ▼
ToolRequirement
```

Candidate generation resolves that requirement through the existing tool
subsystem.

```text
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

Because `ToolStrategy` satisfies the common strategy contract, workflows do not
require a separate tool execution path.

Persisted tool definitions and implementations can therefore be loaded from a
repository, resolved into a workflow candidate, and executed using the existing
workflow runner.

Tool outputs remain structured JSON-compatible values and can be exported as
normal `WorkflowValue` objects.

## Tool Verification

Tool verification executes durable test cases and compares expected outputs
against actual outputs.

Verification provides objective evidence describing implementation correctness.

## Extension Boundary

Tool capability resolution, implementation resolution, execution, and

verification are intentionally separate responsibilities.

Applications may provide additional repositories, runtimes, implementations,

and selection policies without changing the durable tool domain.

The tools package does not define optimization policy.