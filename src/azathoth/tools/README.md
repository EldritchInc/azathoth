# Tools

The `azathoth.tools` package provides durable capability contracts, executable
implementations, deterministic execution, and objective verification.

```text
                 ToolCatalog
                      │
                      ▼
               ToolDefinition
                /           \
               ▼             ▼
 ToolImplementation     ToolTestCase
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

## Tool Definitions

Tool definitions describe immutable capability contracts.

Definitions establish stable interfaces independently of execution environments,
implementation languages, or persistence mechanisms.

## Tool Implementations

Tool implementations describe executable realizations of tool definitions.

Multiple implementations may satisfy the same capability contract.

Implementations identify:

- runtime;
- executable entrypoint; and
- implementation source.

## Tool Execution

Tool executors execute durable tool implementations.

Execution accepts structured inputs and produces structured JSON outputs.

Execution remains independent of verification.

## Tool Verification

Tool verification executes deterministic tool test cases and compares expected
outputs with actual outputs.

Verification produces immutable evidence describing implementation correctness.

Verification remains deterministic and introduces no optimization or heuristic
behavior.

## Tool Catalogs

Tool catalogs provide deterministic discovery of tool definitions.

Catalogs intentionally remain independent of execution, persistence, and
optimization policy.

## Future Direction

The tools subsystem establishes the foundation for future capabilities including:

- persistent tool registries;
- isolated execution environments;
- synthesized tool implementations;
- automatic regression testing;
- capability discovery;
- adaptive tool selection; and
- tool optimization.