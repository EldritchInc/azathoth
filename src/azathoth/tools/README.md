# Tools

The `azathoth.tools` package defines durable capability contracts.

Tools describe **what** a capability does rather than **how** it is executed.

```text
ToolCatalog
      │
      ▼
ToolDefinition
      ├── ToolInputSchema
      ├── ToolOutputSchema
      ├── ToolImplementation
      └── ToolTestCase
```

## Tool Definitions

Tool definitions are immutable capability contracts.

```python
definition = ToolDefinition(
    name="word_count",
    description="Count words in text.",
    version="1.0.0",
    input_schema=input_schema,
    output_schema=output_schema,
)
```

Definitions establish stable interfaces that remain independent of implementation
language, execution environment, and persistence.

## Tool Implementations

Tool implementations describe executable realizations of a capability.

Multiple implementations may satisfy the same tool definition.

```text
word_count
├── python
├── javascript
└── wasm
```

Implementation revisions may evolve without changing the capability contract.

## Tool Test Cases

Tool test cases describe deterministic verification of tool behavior.

They define expected inputs and outputs independently of any specific
implementation.

```text
ToolTestCase
├── inputs
└── expected_output
```

Future execution systems will use tool test cases to validate implementations and
prevent regressions.

## Tool Catalogs

Tool catalogs provide deterministic discovery of tool definitions.

```python
definition = catalog.get(tool_id, "1.0.0")
versions = catalog.versions_for(tool_id)
definitions = catalog.definitions_named("word_count")
```

Catalogs intentionally provide discovery only.

Execution, persistence, optimization, and routing remain responsibilities of
higher-level components.

## Future Direction

Durable tool definitions establish the foundation for future capabilities
including:

- persistent tool registries;
- automatic tool verification;
- synthesized tool implementations;
- capability discovery;
- adaptive tool selection; and
- optimization of executable implementations.