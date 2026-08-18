# ADR 0042: Tool-Backed Workflow Steps

- Status: Accepted
- Date: 2026-08-18

## Context

Azathoth workflows compose executable strategies while keeping workflow
specifications independent from runtime implementations.

Prompt-backed workflow steps already separate:

- model-independent strategy specifications;
- candidate-time model resolution; and
- runtime strategy execution.

Azathoth tools similarly separate:

- durable capability requirements;
- tool definitions;
- executable implementations;
- implementation resolution; and
- execution.

Tools can also be persisted independently from the Azathoth source tree.

Workflows need to use these durable capabilities without embedding tool
implementations or introducing a separate workflow execution path.

## Decision

Workflow steps may be backed by either:

- `PromptStrategySpec`; or
- `ToolStepSpecification`.

A `ToolStepSpecification` contains a `ToolRequirement`.

```text
WorkflowStepSpecification
        │
        └── ToolStepSpecification
                    │
                    ▼
              ToolRequirement
```

Workflow specifications do not reference concrete tool definitions or
implementations.

During workflow candidate generation, tool-backed steps are resolved using the
existing tool resolution infrastructure.

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

The resulting ToolStrategy satisfies the common Strategy protocol.

This allows WorkflowRunner to execute prompt-backed and tool-backed steps
through the same execution path.

## Workflow Inputs

Workflow input bindings continue to use the existing event-backed context
mechanism.

Before a workflow step executes, WorkflowRunner resolves each
WorkflowInputBinding and appends a step-local:

```text
workflow.input.bound
```

context event.

ToolStrategy reads these bound inputs and supplies them as structured
arguments to its ToolExecutor.

```text
WorkflowValue
      │
      ▼
WorkflowInputBinding
      │
      ▼
workflow.input.bound
      │
      ▼
ToolStrategy
      │
      ▼
ToolExecutor
```

No tool-specific input propagation mechanism is introduced.

## Workflow Outputs

Tool execution returns structured JSON-compatible output through the normal
StrategyOutcome contract.

Existing WorkflowValueBinding behavior converts that output into named
workflow values.

```text
ToolExecutor
      │
      ▼
StrategyOutcome
      │
      ▼
WorkflowValueBinding
      │
      ▼
WorkflowValue
```

Tool-produced values can therefore be consumed by downstream workflow steps and
existing workflow conditions.

## Persisted Tools

Tool-backed workflows may resolve tools reconstructed from a
ToolRepository.

```text
SQLiteToolRepository
        │
        ▼
 ToolCatalogLoader
      /          \
     ▼            ▼
ToolCatalog   ToolImplementationCatalog
     │            │
     └─────┬──────┘
           ▼
     Candidate Generation
           │
           ▼
       ToolStrategy
```

The workflow package does not query persistence directly.

Persistence remains below the catalog and resolver boundaries.

## Execution Semantics

Tool-backed workflow steps inherit the existing workflow execution semantics.

This includes:

* dependency ordering;
* input binding;
* output binding;
* conditional execution;
* retries;
* failure policies;
* execution attempts; and
* workflow run evidence.

WorkflowRunner does not contain a separate tool execution path.

It executes the resolved ToolStrategy through the common Strategy
abstraction.

## Consequences

### Positive

* Durable tools can participate directly in workflows.
* Workflow specifications remain independent from concrete implementations.
* Persisted tool source does not need to exist in the Azathoth package.
* Prompt-backed and tool-backed steps use the same workflow runner.
* Existing workflow value propagation works for tool outputs.
* Existing workflow conditions can branch on deterministic tool results.
* Existing retry and failure semantics remain unchanged.
* Tool persistence remains independent from workflow execution.

### Negative

* Tool-backed candidate generation requires configured tool resolution
    infrastructure.
* Tool strategies depend on the workflow input event contract when consuming
    workflow-bound inputs.
* The current Python tool executor runs trusted persisted source in process.

## Alternatives Considered

### Embed ToolImplementation in WorkflowStepSpecification

Rejected because workflow specifications describe durable requirements rather
than runtime implementations.

Embedding implementations would couple workflow specifications to executable
source and bypass existing tool resolution.

### Execute Tools Directly from WorkflowRunner

Rejected because tools already satisfy the common strategy execution model.

Adding a tool-specific runner path would duplicate retry, failure, input,
output, and execution behavior.

### Pass WorkflowInputBinding Objects Directly to ToolStrategy

Rejected because workflow input propagation already has an event-backed
runtime representation.

Using the existing workflow.input.bound context events keeps tool execution
compatible with the common Strategy protocol.

### Resolve Tools During Workflow Execution

Rejected because candidate generation is the boundary where model-independent
workflow specifications become executable runtime candidates.

Tool resolution belongs at the same boundary.

## Result

A persisted deterministic capability can now participate in normal workflow
execution:

```text
Persisted Tool
      │
      ▼
ToolRequirement
      │
      ▼
Candidate Generation
      │
      ▼
ToolStrategy
      │
      ▼
Workflow Execution
      │
      ▼
WorkflowValue
      │
      ▼
WorkflowCondition
      │
      ▼
Downstream Step
```

Tool-backed workflow execution introduces no optimization policy.

It extends the public workflow runtime with deterministic executable
capabilities.