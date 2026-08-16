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
      ToolImplementationResolver
                     │
                     ▼
      ToolImplementationCatalog
                     │
                     ▼
            ToolImplementation
               /            \
              ▼              ▼
      ToolExecutor      ToolTestCase
              │              │
              ▼              │
      PythonToolExecutor     │
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

## Tool Execution

Tool executors execute deterministic implementations using structured inputs
and structured outputs.

Execution remains independent of capability discovery and implementation
selection.

## Tool Verification

Tool verification executes durable test cases and compares expected outputs
against actual outputs.

Verification provides objective evidence describing implementation correctness.

## Future Direction

The implementation subsystem establishes the foundation for future capabilities
including:

- isolated execution environments;
- multiple runtime backends;
- synthesized implementations;
- implementation benchmarking;
- implementation ranking;
- adaptive runtime selection; and
- implementation optimization.