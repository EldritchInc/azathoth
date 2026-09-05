# Tools

`azathoth.tools` defines Azathoth's durable tool capability, implementation,
resolution, execution, and verification architecture.

A tool is not represented as one opaque executable object.

V1 deliberately separates several concepts:

```text
ToolRequirement
      │
      ▼
ToolDefinition
      │
      ▼
ToolImplementation
      │
      ▼
ToolExecutor
      │
      ▼
ToolStrategy
```

with persistence, resolution, and verification remaining independent concerns.

The central architectural distinction is:

```text
capability
    ≠
implementation
    ≠
execution
```

# Architectural Role

The tool subsystem allows workflows to depend on durable capabilities without
embedding runtime execution machinery directly into workflow specifications.

Conceptually:

```text
DURABLE REQUIREMENT

ToolRequirement
      │
      ▼

CAPABILITY RESOLUTION

ToolResolver
      │
      ▼
ToolDefinition
      │
      ▼

IMPLEMENTATION RESOLUTION

ToolImplementationResolver
      │
      ▼
ToolImplementation
      │
      ▼

EXECUTION ADAPTATION

ToolExecutor
      │
      ▼
ToolStrategy
      │
      ▼
Strategy
```

The package also provides:

```text
ToolRepository

ToolCatalog
ToolImplementationCatalog

ToolTestCase
ToolVerifier
ToolVerification
```

These pieces are intentionally separated so that capability identity,
implementation choice, execution, persistence, and empirical verification do
not become one hidden policy layer.

# Public Surface

The V1 tools package exports:

```python
from azathoth.tools import (
    InMemoryToolRepository,
    PythonToolExecutor,
    SQLiteToolRepository,
    ToolCatalog,
    ToolCatalogLoader,
    ToolDefinition,
    ToolEntrypointError,
    ToolExecutionError,
    ToolExecutor,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolMatcher,
    ToolOutputSchema,
    ToolRepository,
    ToolRequirement,
    ToolRequirementMatch,
    ToolRequirements,
    ToolResolver,
    ToolStrategy,
    ToolTestCase,
    ToolTestResult,
    ToolVerification,
    ToolVerifier,
    UnsupportedToolRuntimeError,
    require_tool_repository,
)
```

That public API spans several layers, but those layers retain explicit
responsibility boundaries.

# ToolDefinition

`ToolDefinition` describes a durable, versioned tool capability.

It is immutable.

Conceptually:

```text
ToolDefinition
├── id
├── name
├── description
├── version
├── input_schema
└── output_schema
```

A tool definition answers:

```text
What capability exists?

What structured input does it accept?

What structured output does it promise?
```

It does not answer:

```text
Which implementation executes it?

Which runtime executes that implementation?

Which implementation should be preferred?
```

Those are separate concerns.

# Tool Identity and Version

A tool definition has:

```text
id

version
```

The pair:

```text
(tool id, tool version)
```

identifies one exact durable capability contract.

The same tool identity may therefore have multiple definition versions.

Conceptually:

```text
Tool ID
   │
   ├── version 1.0.0
   ├── version 2.0.0
   └── version 3.0.0
```

This allows capability evolution without conflating versions of the contract.

# ToolInputSchema

`ToolInputSchema` wraps structured JSON-compatible schema data describing a
tool's expected input.

```text
ToolInputSchema
└── json_schema
```

The schema itself is durable data.

It is not executable validation code or a runtime adapter.

# ToolOutputSchema

`ToolOutputSchema` similarly describes the structured output contract.

```text
ToolOutputSchema
└── json_schema
```

Together:

```text
input schema
     │
     ▼
ToolDefinition
     │
     ▼
output schema
```

describe the capability boundary independently from any implementation source.

# Capability Is Not Implementation

The fundamental tool-domain distinction is:

```text
ToolDefinition
    capability contract

ToolImplementation
    executable realization
```

A tool definition may exist even when no executable implementation is
available in the current runtime.

Likewise, multiple implementations may realize the same exact tool definition.

```text
ToolDefinition
      │
      ├── ToolImplementation A
      ├── ToolImplementation B
      └── ToolImplementation C
```

Capability identity therefore does not imply implementation identity.

# ToolRequirement

`ToolRequirement` describes one required capability.

It is immutable and contains:

```text
name

optional version

optional runtime
```

Example:

```python
from azathoth.tools import ToolRequirement

requirement = ToolRequirement(
    name="word_count",
    version="1.0.0",
    runtime="python",
)
```

These fields participate at different stages of resolution.

That distinction matters.

# Requirement Semantics

The capability portion of a requirement is:

```text
name

optional version
```

The runtime portion is:

```text
optional runtime
```

V1 does not treat runtime as part of capability-definition matching.

Instead:

```text
name/version
    │
    ▼
ToolDefinition resolution

runtime
    │
    ▼
ToolImplementation resolution
```

This keeps:

```text
what capability is required
```

separate from:

```text
what kind of implementation may realize it
```

# ToolRequirements

`ToolRequirements` is an immutable ordered collection of
`ToolRequirement` objects.

```text
ToolRequirements
├── requirement 1
├── requirement 2
└── requirement 3
```

Resolution preserves declaration order.

This gives callers deterministic correspondence between requested capabilities
and their resolution results.

# ToolMatcher

`ToolMatcher` defines deterministic capability matching.

For one definition and one requirement:

```text
definition.name
    must equal
requirement.name
```

If the requirement has a version:

```text
definition.version
    must equal
requirement.version
```

If the requirement version is absent, every version with the matching name may
match.

Conceptually:

```text
ToolRequirement(
    name="word_count",
    version=None,
)
        │
        ▼
word_count 1.0.0
word_count 2.0.0
word_count 3.0.0
```

assuming those definitions exist in catalog order.

# Runtime Does Not Affect Definition Matching

`ToolMatcher` does not inspect the requirement's runtime.

This is intentional.

```text
ToolMatcher
    capability matching

ToolImplementationResolver
    runtime constraint matching
```

A Python requirement and JavaScript requirement still refer to the same durable
tool capability if their name and version match.

The runtime determines which implementation is acceptable, not which
capability definition exists.

# ToolRequirementMatch

`ToolRequirementMatch` records whether a requirement matched at least one
definition.

```text
ToolRequirementMatch
├── requirement
└── matched
```

It is an immutable result of capability matching.

It does not contain implementation choice or execution evidence.

# ToolCatalog

`ToolCatalog` is an immutable reproducible inventory of durable
`ToolDefinition` objects.

```text
ToolCatalog
└── definitions: tuple[ToolDefinition, ...]
```

Catalog order is preserved.

The catalog rejects duplicate references for the same:

```text
(tool id, tool version)
```

pair.

This ensures one exact capability reference appears at most once in a catalog.

# ToolCatalog Queries

V1 supports exact and grouped lookup.

An exact definition may be resolved by:

```text
tool id + version
```

The catalog may also return:

```text
all definitions for one tool ID

all versions for one tool ID

all definitions with one exact name
```

The catalog does not rank or optimize those results.

It is immutable inventory.

# ToolResolver

`ToolResolver` performs deterministic capability resolution over a
`ToolCatalog`.

```text
ToolRequirement
      │
      ▼
ToolResolver
      │
      ▼
ToolMatcher
      │
      ▼
ToolDefinition(s)
```

Resolution preserves catalog order.

For example, if the catalog contains:

```text
word_count 1.0.0
word_count 2.0.0
```

then:

```text
ToolRequirement(
    name="word_count",
)
```

may resolve both definitions in that same order.

An exact version requirement resolves only matching definitions.

Unknown capabilities or versions resolve to an empty tuple.

# Empty Resolution Is Explicit

`ToolResolver.resolve()` does not manufacture a fallback.

```text
unknown requirement
      │
      ▼
()
```

Likewise:

```text
requested version unavailable
      │
      ▼
()
```

Higher-level candidate generation determines what such a failure means for the
workflow being constructed.

The tool resolver itself remains deterministic and policy-light.

# ToolImplementation

`ToolImplementation` describes a durable, versioned executable realization of
one exact tool definition.

It is immutable.

Conceptually:

```text
ToolImplementation
├── id
├── tool_id
├── tool_version
├── version
├── runtime
├── entrypoint
└── source
```

Several identities therefore coexist deliberately:

```text
tool_id
    capability identity

tool_version
    capability contract version

implementation id
    implementation identity

implementation version
    implementation version
```

These must not be collapsed.

# Implementation Version Versus Tool Version

Consider:

```text
ToolDefinition
    tool_id = A
    version = 2.0.0
```

An implementation may be:

```text
ToolImplementation
    id = X
    tool_id = A
    tool_version = 2.0.0
    version = 1.3.0
```

The two versions mean different things.

```text
tool_version
    version of the capability contract implemented

version
    version of this implementation artifact
```

This separation allows implementation changes without redefining the tool
capability itself.

# Runtime

`ToolImplementation.runtime` names the execution runtime required by the
implementation.

Example:

```text
python
```

Runtime is implementation metadata.

It is not part of the `ToolDefinition`.

That means the same capability contract can theoretically have multiple
runtime realizations:

```text
ToolDefinition
      │
      ├── Python implementation
      ├── JavaScript implementation
      └── other implementation
```

subject to available executors.

# Entrypoint

`ToolImplementation.entrypoint` identifies the callable entrypoint inside the
implementation source.

V1 defaults this field to:

```text
run
```

The executor owns interpreting that entrypoint according to the implementation
runtime.

# Source

`ToolImplementation.source` stores the implementation source as durable data.

This is a major architectural distinction:

```text
durable implementation description
    =
ToolImplementation

execution machinery
    =
ToolExecutor
```

The implementation contains what should be executed.

The executor provides the runtime semantics for executing it.

# ToolImplementationCatalog

`ToolImplementationCatalog` is an immutable ordered inventory of durable
implementation artifacts.

```text
ToolImplementationCatalog
└── implementations: tuple[ToolImplementation, ...]
```

Duplicate implementation identifiers are rejected.

The catalog supports:

```text
exact implementation lookup

all implementations for one tool identity

all implementations for one exact tool definition version
```

Catalog order is preserved.

# Implementation Resolution

`ToolImplementationResolver` maps a resolved `ToolDefinition` to
implementations for that exact capability version.

```text
ToolDefinition
      │
      ▼
(tool id, version)
      │
      ▼
ToolImplementationCatalog
      │
      ▼
matching implementations
```

The resolver requires:

```text
implementation.tool_id
    =
definition.id

implementation.tool_version
    =
definition.version
```

This prevents an implementation targeting one version of a capability from
silently executing for another version.

# Runtime-Constrained Implementation Resolution

When resolving for a full `ToolRequirement`, the implementation resolver can
also apply its optional runtime constraint.

```text
ToolDefinition
      │
      ▼
exact matching implementations
      │
      ▼
requirement.runtime
      │
      ▼
runtime-compatible implementations
```

If no runtime is specified:

```text
all exact-definition implementations
```

are returned.

If a runtime is specified:

```text
implementation.runtime == requirement.runtime
```

must also hold.

# Resolution Does Not Rank Implementations

`ToolImplementationResolver` returns matching implementations.

It does not decide which one is "best."

```text
resolution
    ≠
ranking

resolution
    ≠
optimization
```

If multiple matching implementation artifacts exist, that multiplicity remains
explicit for higher-level policy.

The resolver does not silently introduce:

```text
cheapest selection

fastest selection

latest-version preference

arbitrary first-item preference
```

as optimization policy.

# ToolExecutor

`ToolExecutor` is the runtime execution protocol.

It defines:

```python
async def execute(
    implementation: ToolImplementation,
    inputs: dict[str, JsonValue],
) -> dict[str, JsonValue]: ...
```

The boundary is therefore:

```text
ToolImplementation
        +
structured inputs
        │
        ▼
ToolExecutor
        │
        ▼
structured output
```

The protocol does not require a specific runtime implementation.

# Tool Implementation Is Not Tool Executor

Another critical distinction is:

```text
ToolImplementation
    durable executable artifact

ToolExecutor
    process-local execution service
```

The implementation may be persisted and reconstructed.

The executor is runtime behavior.

This mirrors Azathoth's broader separation between durable intent and
process-local executable services.

# PythonToolExecutor

V1 provides `PythonToolExecutor`.

It executes trusted Python tool implementations in process.

```text
ToolImplementation(runtime="python")
        │
        ▼
PythonToolExecutor
        │
        ▼
load source
        │
        ▼
resolve entrypoint
        │
        ▼
call with structured inputs
        │
        ▼
structured output
```

The executor supports both synchronous and awaitable entrypoint results.

# Trusted In-Process Execution

`PythonToolExecutor` is explicitly an executor for trusted Python
implementations.

It evaluates implementation source in process using a constrained builtin
namespace.

This is not a general-purpose operating-system sandbox.

The architectural guarantee is narrower:

```text
known runtime
+
controlled execution path
+
structured input/output validation
```

Applications must not interpret in-process tool execution as isolation of
untrusted arbitrary code.

# Supported Runtime

The Python executor validates that the implementation runtime is one it
supports.

Unsupported runtimes raise:

```text
UnsupportedToolRuntimeError
```

An executor therefore does not silently attempt to interpret implementation
source using the wrong runtime.

# Entrypoint Validation

If implementation source cannot provide the configured callable entrypoint,
execution raises:

```text
ToolEntrypointError
```

This makes invalid implementation configuration explicit.

# Execution Failure

Tool execution failures derive from:

```text
ToolExecutionError
```

Execution exceptions from the implementation are translated into this tool
execution boundary.

The caller receives an explicit failure rather than an arbitrary implementation
exception leaking as architectural policy.

# Structured Outputs

`ToolExecutor` returns:

```text
dict[str, JsonValue]
```

`PythonToolExecutor` validates implementation output against that structured
JSON-compatible boundary.

If an implementation produces invalid output, execution fails with
`ToolExecutionError`.

This means tool execution does not inject arbitrary live Python objects into
workflow value propagation.

# Capability Schema Versus Runtime Output Validation

The V1 implementation contains two distinct concepts:

```text
ToolOutputSchema
    durable capability contract metadata

executor output type validation
    runtime JSON-compatible structural boundary
```

These should not be confused.

The frozen Python executor validates that returned output is a structured
JSON-compatible dictionary.

The tool package does not make the executor itself a general JSON Schema
validation engine for `ToolOutputSchema`.

# ToolStrategy

`ToolStrategy` adapts one resolved tool implementation to Azathoth's common
`Strategy` contract.

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

It exposes:

```text
StrategyMetadata

resolved ToolImplementation

async run(Context) -> StrategyOutcome
```

This means workflow execution does not require an entirely separate generic
execution abstraction for tools.

# ToolStrategy Runtime Binding

A `ToolStrategy` contains:

```text
metadata
implementation
executor
```

The implementation identifies the durable executable artifact.

The executor provides process-local execution mechanics.

```text
durable implementation
        +
runtime executor
        │
        ▼
executable ToolStrategy
```

Like prompt-backed strategies, the resulting strategy is a runtime realization.

# Workflow-Bound Tool Inputs

`ToolStrategy` extracts structured inputs from the workflow step context.

It looks for context events of type:

```text
workflow.input.bound
```

produced by:

```text
workflow-runner
```

Each valid input event contains:

```text
name

value
```

Conceptually:

```text
workflow value binding
        │
        ▼
ContextEvent(
    event_type="workflow.input.bound",
    producer="workflow-runner",
)
        │
        ▼
ToolStrategy
        │
        ▼
dict[str, JsonValue]
        │
        ▼
ToolExecutor
```

This connects tool execution to the common immutable context architecture.

# Workflow Input Validation

`ToolStrategy` rejects malformed workflow-bound input events.

A bound input name must be a non-empty string.

A bound input must contain a value.

The same input name cannot be bound more than once.

Invalid bindings raise:

```text
ToolExecutionError
```

This prevents ambiguous or malformed workflow context from being silently
turned into tool arguments.

# ToolStrategy Outcome

After execution:

```text
ToolExecutor
    │
    ▼
dict[str, JsonValue]
    │
    ▼
StrategyOutcome.output
```

The tool strategy returns the structured tool output through the common
strategy abstraction.

It does not implement workflow output routing itself.

# Tool Requirements in Workflows

Workflow specifications can declare tool-backed steps through
`ToolStepSpecification`.

The durable relationship is:

```text
WorkflowStepSpecification
        │
        ▼
ToolStepSpecification
        │
        ▼
ToolRequirement
```

The workflow does not need to persist a live `ToolExecutor`.

Instead, candidate generation resolves the requirement using runtime tool
composition.

# Tool Candidate Generation

The V1 tool-backed workflow path is:

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
      │
      ▼
WorkflowCandidateStep
```

This mirrors the model-backed architecture:

```text
durable requirement
      │
      ▼
runtime resolution
      │
      ▼
executable candidate
```

# Tools Do Not Own Workflow Orchestration

`ToolStrategy` executes one resolved implementation.

It does not own:

```text
dependency ordering

workflow input/output mapping

conditions

retries

failure policies

workflow completion

workflow persistence
```

Those remain responsibilities of `azathoth.workflows`.

The distinction is:

```text
tool execution
    ≠
workflow orchestration
```

# ToolRepository

`ToolRepository` is the persistence contract for durable tool artifacts.

It persists three artifact types:

```text
ToolDefinition

ToolImplementation

ToolTestCase
```

The repository exposes independent save, get, and ordered collection operations
for each.

It does not execute or resolve any of them.

# Repository Semantics

Current repository implementations include:

```text
InMemoryToolRepository

SQLiteToolRepository
```

Both persist durable domain artifacts.

Repository responsibility ends at storage and reconstruction.

```text
ToolRepository
    stores artifacts

ToolResolver
    resolves capability

ToolImplementationResolver
    resolves implementation

ToolExecutor
    executes implementation

ToolVerifier
    verifies implementation
```

These responsibilities are deliberately separate.

# Durable Artifacts Are Append-Oriented

The current repository implementations reject replacement of an already stored
artifact identity.

That means definitions, implementations, and test cases behave as explicit
durable artifacts rather than mutable records silently overwritten under the
same identity.

Changes should be represented through appropriate new durable identity or
version semantics instead of accidental replacement.

# ToolCatalogLoader

`ToolCatalogLoader` reconstructs immutable runtime-facing tool artifacts from a
repository.

It can load:

```text
ToolCatalog

ToolImplementationCatalog

ToolTestCase tuple
```

Conceptually:

```text
ToolRepository
      │
      ▼
ToolCatalogLoader
      │
      ├── ToolCatalog
      ├── ToolImplementationCatalog
      └── ToolTestCase(s)
```

The loader reconstructs data.

It does not resolve capabilities, choose implementations, or execute tools.

# Persistence Versus Runtime Composition

After reconstruction:

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

These resolver instances are process-local runtime services.

The persistent catalogs themselves remain immutable data.

This maintains the broader Azathoth rule:

```text
persist durable artifacts

compose runtime behavior
```

# Runtime Composition

`AzathothRuntime` carries:

```text
ToolCatalog

ToolImplementationCatalog

ToolResolver

ToolImplementationResolver
```

The runtime constructs its resolvers from the supplied catalogs.

Conceptually:

```text
persisted/reconstructed ToolCatalog
             │
             ▼
        ToolResolver

persisted/reconstructed ToolImplementationCatalog
             │
             ▼
   ToolImplementationResolver
```

The runtime does not move resolution logic into persistence.

# ToolTestCase

`ToolTestCase` is an immutable durable verification case.

It contains:

```text
id

tool_id

name

description

inputs

expected_output
```

Both inputs and expected output use structured JSON-compatible values.

A test case expresses:

```text
Given these inputs

this tool capability is expected to produce this output
```

It is durable evidence intent, not an executor.

# Test Case Identity

A test case belongs to:

```text
tool_id
```

and has its own independent UUID identity.

The V1 test-case model does not contain an implementation ID.

That means test cases describe expected behavior for the tool capability and
can be applied when verifying a concrete implementation.

# ToolVerifier

`ToolVerifier` executes a `ToolImplementation` against durable
`ToolTestCase` objects using a supplied `ToolExecutor`.

```text
ToolImplementation
        +
ToolTestCase(s)
        +
ToolExecutor
        │
        ▼
ToolVerifier
        │
        ▼
ToolVerification
```

Verification therefore reuses the same execution abstraction rather than
implementing a separate tool runtime.

# ToolTestResult

Every verification case produces a `ToolTestResult`.

It contains:

```text
test_case_id

passed

expected_output

actual_output

duration_seconds
```

Pass/fail is determined by exact equality:

```text
actual_output == expected_output
```

The result therefore records both the judgment and the evidence used to make
it.

# ToolVerification

`ToolVerification` aggregates the results for one implementation.

It contains:

```text
implementation_id

results

verified_at
```

and derives:

```text
passed_count

failed_count

pass_rate

passed
```

An empty verification does not pass.

```text
results = ()
    │
    ▼
passed = False
pass_rate = 0.0
```

Verification therefore requires actual evidence.

# Verification Is Not Capability Resolution

Verification asks:

```text
Does this implementation satisfy these test cases?
```

Capability resolution asks:

```text
Which tool definitions satisfy this requirement?
```

These are different operations.

```text
resolution
    ≠
verification
```

Likewise, implementation resolution asks:

```text
Which implementation artifacts target this exact definition?
```

It does not assert those implementations are correct.

# Verification Is Not Optimization

`ToolVerification` produces objective implementation evidence.

It does not rank multiple implementations or automatically select a winner.

```text
verification
    ≠
optimization

pass rate
    ≠
deployment policy
```

Higher-level systems may use verification evidence when making decisions, but
the tool subsystem does not introduce that policy.

# Definition Is Not Availability

A durable `ToolDefinition` existing in the catalog means:

```text
this capability is configured
```

It does not guarantee:

```text
a compatible implementation exists
```

The distinction is:

```text
ToolCatalog
      │
      ▼
capability available for resolution

ToolImplementationCatalog
      │
      ▼
implementation artifacts available for resolution
```

Both layers must succeed before executable tool behavior can be composed.

# Implementation Metadata Is Not Runtime Support

Likewise, a `ToolImplementation` may declare:

```text
runtime="javascript"
```

while the current process only has a Python executor.

That implementation artifact can still exist durably.

Whether it can execute depends on the available `ToolExecutor`.

Therefore:

```text
implementation exists
    ≠
current executor supports it
```

# ToolStrategy Is Not Durable Capability

A `ToolStrategy` is a runtime adapter around:

```text
ToolImplementation
+
ToolExecutor
```

It should not be confused with the durable capability definition.

```text
ToolDefinition
    what the capability promises

ToolImplementation
    one durable realization

ToolStrategy
    runtime strategy adapter

ToolExecutor
    execution mechanics
```

All four serve different purposes.

# Tool Schema Is Not Source

Another important distinction is:

```text
ToolDefinition
    input/output contract

ToolImplementation
    executable source
```

The definition does not embed executable code.

The implementation does not redefine the durable capability contract.

That separation allows multiple implementation artifacts to target the same
stable definition.

# Tool Execution Is Not Provider Execution

Tools use their own `ToolExecutor` protocol.

They are not modeled as language models and do not depend on provider model
registries.

```text
ToolExecutor
    ≠
LanguageModel

ToolImplementation
    ≠
ModelMetadata
```

Both domains follow similar durable/runtime separation principles while
remaining distinct abstractions.

# Tool Architecture and Strategies

`ToolStrategy` satisfies Azathoth's common executable strategy contract.

This yields:

```text
ToolDefinition
      │
      ▼
ToolImplementation
      │
      ▼
ToolStrategy
      │
      ▼
Strategy
      │
      ▼
StrategyOutcome
```

Execution infrastructure can therefore treat a tool-backed workflow step
through the same broad executable boundary used elsewhere.

The tool package still retains tool-specific implementation and execution
semantics beneath that adapter.

# Tool Architecture and Workflows

Workflows own durable orchestration.

Tools own capability and implementation semantics.

```text
WorkflowSpecification
        │
        ▼
ToolStepSpecification
        │
        ▼
ToolRequirement
        │
        ▼
tool resolution
        │
        ▼
ToolStrategy
        │
        ▼
WorkflowCandidate
```

This allows a durable workflow to express:

```text
I require this tool capability
```

rather than:

```text
instantiate this process-local executor object
```

# Tool Architecture and Runtime

Runtime composition connects reconstructed durable tool state with resolution
services.

```text
ToolRepository
      │
      ▼
ToolCatalogLoader
      │
      ├── ToolCatalog
      │       │
      │       ▼
      │   ToolResolver
      │
      └── ToolImplementationCatalog
              │
              ▼
      ToolImplementationResolver
```

Those pieces become part of the runtime snapshot used by candidate generation.

# Tool Architecture and Persistence

Persistence contains:

```text
definitions

implementations

test cases
```

It does not contain:

```text
ToolResolver

ToolImplementationResolver

ToolExecutor

ToolVerifier execution state

ToolStrategy
```

Those are runtime/application services.

This preserves the boundary:

```text
durable data
    ≠
runtime behavior
```

# Tool Architecture and Optimization

The tools subsystem does not define a policy for selecting among multiple
capability definitions or implementations based on cost, latency, quality, or
other empirical evidence.

Resolution is deterministic matching.

Verification is deterministic evidence.

Optimization is a separate concern.

```text
matching
    ≠
ranking

verification
    ≠
selection

resolution
    ≠
optimization
```

# Complete V1 Tool Architecture

```text
                         DURABLE INTENT

                       ToolRequirement
                             │
                             ▼

                     CAPABILITY LAYER

                        ToolCatalog
                             │
                             ▼
                        ToolResolver
                             │
                             ▼
                       ToolDefinition
                  ┌──────────┴──────────┐
                  │                     │
                  ▼                     ▼
             input schema          output schema
                  │                     │
                  └──────────┬──────────┘
                             │
                             ▼

                    IMPLEMENTATION LAYER

               ToolImplementationCatalog
                             │
                             ▼
               ToolImplementationResolver
                             │
                             ▼
                    ToolImplementation
                  ┌──────────┼───────────┐
                  │          │           │
                  ▼          ▼           ▼
               runtime   entrypoint    source
                  │
                  └──────────┬───────────┘
                             │
                             ▼

                       EXECUTION LAYER

                       ToolExecutor
                             │
                             ▼
                      ToolStrategy
                             │
                             ▼
                         Strategy
                             │
                             ▼
                    StrategyOutcome


                       VERIFICATION LAYER

                    ToolTestCase(s)
                         +
                    ToolImplementation
                         +
                     ToolExecutor
                         │
                         ▼
                     ToolVerifier
                         │
                         ▼
                   ToolVerification
```

Persistence sits beside those runtime layers:

```text
ToolDefinition
ToolImplementation
ToolTestCase
       │
       ▼
ToolRepository
       │
       ▼
ToolCatalogLoader
       │
       ▼
immutable reconstructed catalogs
```

# V1 Tool Principles

The V1 tool architecture can be summarized as:

```text
capability
    ≠
implementation

tool version
    ≠
implementation version

requirement matching
    ≠
implementation resolution

implementation existence
    ≠
runtime support

resolution
    ≠
execution

execution
    ≠
verification

verification
    ≠
optimization

durable artifacts
    ≠
runtime services

tool strategy
    ≠
workflow orchestration
```

The central rule is:

```text
Persist the capability.

Persist its implementations.

Resolve explicitly.

Execute through a runtime boundary.

Verify with durable evidence.
```

That gives Azathoth a tool architecture where workflows can depend on stable
capabilities while executable implementations remain versioned, resolvable,
testable, and operationally separate.