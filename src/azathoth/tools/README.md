# Tools

The `azathoth.tools` package provides durable capability definitions,
implementations, deterministic execution, verification, and capability
resolution.

```text
                 ToolRequirements
                        │
                        ▼
                 ToolRequirement
                        │
                        ▼
                   ToolResolver
                  /            \
                 ▼              ▼
          ToolCatalog      ToolMatcher
                 \              /
                  ▼            ▼
                 ToolDefinition
                  /           \
                 ▼             ▼
      ToolImplementation   ToolTestCase
                 │             │
                 ▼             │
          ToolExecutor         │
                 │             │
                 └──────┬──────┘
                        ▼
                  ToolVerifier
                        │
                        ▼
                ToolVerification
```

## Tool Requirements

Tool requirements describe capabilities required by higher-level systems.

Requirements intentionally describe *what* capability is needed rather than
*which* implementation should execute.

## Tool Resolution

Tool resolution converts durable requirements into candidate tool definitions.

Resolution combines immutable catalogs with deterministic matching.

Resolution introduces no ranking or optimization policy.

## Tool Definitions

Tool definitions describe immutable capability contracts.

Definitions remain independent of implementation language, execution
environment, and persistence.

## Tool Implementations

Tool implementations provide executable realizations of capability definitions.

Multiple implementations may satisfy the same capability.

## Tool Execution

Tool executors execute implementations using structured inputs and structured
outputs.

Execution remains independent of verification.

## Tool Verification

Tool verification executes durable test cases and compares expected outputs with
actual outputs.

Verification provides objective evidence describing implementation correctness.

## Future Direction

The tools subsystem establishes the foundation for future capabilities
including:

- implementation resolution;
- runtime selection;
- persistent tool registries;
- synthesized tool implementations;
- adaptive capability routing;
- capability optimization; and
- workflow capability planning.