# ADR 0056: Execute Configured Workflows From the CLI

- Status: Accepted
- Date: 2026-08-23

## Context

Azathoth's command-line application can already manage the durable portion of
the workflow lifecycle.

```text
workflow JSON
      │
      ▼
workflow import
      │
      ▼
durable persistence
      │
      ├── workflow list
      └── workflow show
```

The runtime subsystem can reconstruct durable workflow, model, and tool
configuration and generate executable workflow candidates by stable workflow
identity.

The workflow subsystem already provides `WorkflowRunner` for executing those
candidates and recording complete `WorkflowRun` evidence.

Before this decision, however, the installed application did not connect those
two existing boundaries.

Users could import and inspect workflows but could not request execution from
the command line.

## Decision

The CLI provides:

```text
azathoth workflow run <WORKFLOW_ID>
```

Workflow execution composes the existing runtime candidate-generation boundary
with the existing workflow runner.

```text
workflow ID
    │
    ▼
AzathothRuntime
    │
    ▼
generate_workflow_candidate()
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

The CLI does not introduce an alternative workflow execution path.

## Configured Workflow Execution Service

The CLI application layer provides:

```text
execute_configured_workflow()
```

This operation accepts:

- a `RuntimeEnvironment`;
- a workflow UUID;
- an optional initial `Context`; and
- an optional `WorkflowRunner`.

It performs:

```text
RuntimeEnvironment
      │
      ▼
generate_workflow_candidate(workflow_id)
      │
      ▼
WorkflowCandidate
      │
      ▼
WorkflowRunner.run(candidate, context)
      │
      ▼
WorkflowRun
```

The service contains no:

- argument parsing;
- environment-variable access;
- persistence logic;
- output rendering; or
- provider-specific model-selection policy.

It exists only to compose already-supported application boundaries.

## Runtime Boundary

`AzathothRuntime` remains responsible for runtime composition and candidate
generation.

It does not execute workflows.

```text
AzathothRuntime
      │
      ▼
WorkflowCandidate
```

Execution remains owned by:

```text
WorkflowRunner
      │
      ▼
WorkflowRun
```

The CLI application service composes these operations without changing either
subsystem's responsibility.

## Candidate Generation

Workflow execution uses the existing runtime candidate-generation semantics.

For prompt-backed steps:

```text
ModelRequirements
      │
      ▼
ModelCatalog
      │
      ▼
eligible configured models
      │
      ▼
LanguageModelRegistry
      │
      ▼
executable prompt candidates
```

The first executable candidate in deterministic configured catalog order is
used by the existing workflow generation logic.

The CLI does not accept a global model argument and does not introduce a
single-model execution environment variable.

Different workflow steps therefore retain independent model requirements and
may resolve to different configured models.

## Tool-Backed Steps

Tool-backed workflow steps continue to resolve through the runtime's existing
tool boundaries.

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
executable tool strategy
```

The CLI does not special-case tool execution.

## Initial Context

`execute_configured_workflow()` accepts an optional initial `Context`.

When none is supplied, execution begins with an empty context.

```text
no supplied context
       │
       ▼
    Context()
       │
       ▼
WorkflowRunner
```

This establishes a default CLI execution path while preserving the application
service's ability to receive context from future command-line input,
benchmarks, or other application interfaces.

## CLI Command

The command syntax is:

```bash
azathoth workflow run <WORKFLOW_ID>
```

The command:

```text
CLI arguments
      │
      ▼
CliRuntimeConfiguration
      │
      ▼
load_runtime()
      │
      ▼
execute_configured_workflow()
      │
      ▼
WorkflowRun
```

A malformed workflow UUID remains an argument-parser error.

A syntactically valid workflow identifier absent from the configured runtime
remains a runtime configuration failure.

## Execution Failures

Two failure classes remain distinct.

### Candidate Cannot Be Produced

Failures such as:

- workflow not configured;
- no executable prompt candidate;
- unavailable tool capability; or
- unavailable tool implementation

occur before a `WorkflowRun` exists.

```text
workflow ID
    │
    ▼
candidate generation
    │
    ╳
    ▼
no WorkflowRun
```

These failures are rendered as application errors and return a nonzero process
status.

### Completed Run Contains Failed Steps

Strategy failures occurring during workflow execution are recorded by
`WorkflowRunner`.

```text
WorkflowCandidate
      │
      ▼
WorkflowRunner
      │
      ▼
WorkflowRun
      │
      └── failed step evidence
```

A failed `WorkflowRun` is still a valid execution result.

The CLI therefore renders the run evidence and exits nonzero rather than
replacing that result with a generic application error.

## Workflow Run Rendering

The CLI renders completed workflow runs using the evidence already present in
`WorkflowRun`.

The workflow-level view includes:

```text
Workflow
Workflow ID
Run ID
Status
Duration
Steps
Executed
Failed
Skipped
Retries
```

Each workflow step includes:

```text
Step
ID
Status
Attempts
```

Successfully executed steps additionally include:

```text
Strategy
Provider
Model
Prompt Tokens
Completion Tokens
Total Tokens
Latency
Estimated Cost
Output
```

Fields backed by optional execution metrics are omitted when they were not
recorded.

Failed steps include the final recorded failure type and message.

## Output Rendering

Strategy outputs are JSON-compatible values.

The CLI therefore renders outputs as JSON rather than Python object
representations.

For example:

```text
Output:
"success"
```

or:

```text
Output:
{
  "classification": "positive",
  "confidence": 0.98
}
```

This preserves the distinction between textual and structured workflow output.

## Provider-Neutral Metrics

Execution rendering consumes the provider-neutral strategy metrics already
recorded by Azathoth.

Current metrics may include:

- provider;
- model;
- prompt tokens;
- completion tokens;
- total tokens;
- latency; and
- estimated cost.

The CLI performs no provider-specific metric extraction.

## Requested Versus Resolved Provider Model

Provider responses may contain more detailed runtime identity information than
the current durable `ExecutionResult` retains.

For example, OpenRouter may distinguish:

```text
configured model
resolved provider model
```

The current workflow run evidence retains the provider-neutral model metric but
does not retain a separate resolved-model field.

The CLI therefore renders only model identity actually present in durable
execution evidence.

A future change may extend execution metrics if resolved provider identity is
required for optimization provenance.

## Workflow-Level Cost and Token Aggregation

The CLI does not independently sum workflow token usage or cost.

Workflow-level rendering uses aggregates owned by `WorkflowRun`, such as:

- step counts;
- retry count; and
- duration.

Step-level execution metrics expose token usage and estimated cost.

If workflow-wide token and cost aggregates are required, they should first
become workflow-domain properties rather than arithmetic duplicated in the CLI
renderer.

## Process Status

A successfully completed workflow returns:

```text
exit 0
```

A completed `WorkflowRun` containing failed steps returns:

```text
exit 1
```

Candidate-generation or runtime-configuration failures also return:

```text
exit 1
```

Malformed command syntax remains owned by the argument parser and returns its
normal parser error status.

## Model Configuration Requirement

Workflow execution depends on more than durable workflow configuration.

A prompt-backed workflow requires:

```text
WorkflowSpecification
        +
ModelMetadata
        +
executable provider configuration
```

The CLI runtime reconstructs `ModelCatalog` from durable model metadata.

For OpenRouter, executable implementations are attached from that reconstructed
catalog when `OPENROUTER_API_KEY` is configured.

```text
SQLiteModelRepository
        │
        ▼
ModelCatalog
        │
        +
OPENROUTER_API_KEY
        │
        ▼
LanguageModelRegistry
```

Therefore importing a workflow alone does not make a prompt-backed workflow
executable.

## Model CLI Gap

The CLI does not yet provide a supported user-facing command for adding model
metadata to the configured application database.

A user can currently:

```text
workflow import
workflow list
workflow show
workflow run
```

but `workflow run` requires compatible model metadata already present in the
configured database.

This is the next application usability gap.

The intended next command family is:

```text
azathoth model import <FILE>
azathoth model list
azathoth model show <MODEL_IDENTIFIER>
```

This will give users an application-native path for configuring the model
catalog before end-to-end workflow execution is documented as a complete fresh
installation journey.

## Installed End-to-End Execution

This decision deliberately does not claim a complete installed
workflow-import-to-execution lifecycle yet.

An end-to-end test that pre-seeded model metadata through Python would prove the
underlying runtime path but would not prove the intended user-facing product
journey.

The stronger future proof is:

```text
model JSON
    │
    ▼
model import
    │
    ▼
ModelCatalog

workflow JSON
    │
    ▼
workflow import
    │
    ▼
WorkflowCatalog

provider credentials
    │
    ▼
LanguageModelRegistry

WorkflowCatalog
ModelCatalog
LanguageModelRegistry
    │
    ▼
workflow run
    │
    ▼
WorkflowRun
```

Installed-console execution coverage is therefore deferred until model
configuration can also be performed through the application.

## Consequences

### Positive

- The CLI can execute configured workflow specifications.
- Execution reuses existing runtime and workflow boundaries.
- Runtime composition does not become responsible for workflow execution.
- Model selection remains requirement-driven and step-specific.
- Tool resolution remains unchanged.
- Completed workflow failures retain their execution evidence.
- Human-readable output exposes real workflow-run data.
- Structured strategy outputs render correctly as JSON.
- Optional provider metrics render only when available.
- CLI rendering introduces no provider-specific logic.

### Negative

- Prompt-backed workflow execution still requires model metadata to have been
  configured outside the CLI.
- The installed CLI does not yet provide a complete fresh-user execution
  journey.
- Workflow runs are not automatically persisted by the CLI.
- Workflow-wide token and cost totals are not currently rendered.
- Resolved provider model identity is not separately preserved in
  `WorkflowRun`.

## Alternatives Considered

### Add Workflow Execution to `AzathothRuntime`

Rejected.

The runtime is the process-local composition and candidate-generation boundary.

`WorkflowRunner` already owns execution.

### Execute Candidates Directly in the CLI Command Handler

Rejected.

Application orchestration should remain independently testable and free from
argument parsing or terminal rendering.

### Add `--model` to `workflow run`

Rejected.

Model resolution already derives from durable `ModelRequirements` and the
configured model catalog.

A global CLI model option would weaken step-specific model selection.

### Restore a Single Global OpenRouter Model Environment Variable

Rejected.

The runtime supports multiple configured OpenRouter models and independent
model resolution across workflow steps.

### Hide Failed Workflow Runs Behind Generic Error Output

Rejected.

A failed `WorkflowRun` is valuable execution evidence and should remain visible
to operators.

### Aggregate Workflow Cost and Tokens in the Renderer

Rejected.

Domain-level aggregates should be owned by the workflow model before they are
presented by the CLI.

### Add Installed End-to-End Execution Before Model CLI Configuration

Deferred.

A test requiring hidden Python model seeding would not represent the desired
user-facing lifecycle.

## Result

Azathoth's CLI can now cross from durable workflow configuration into actual
execution.

```text
configured workflow
      │
      ▼
candidate generation
      │
      ▼
WorkflowCandidate
      │
      ▼
WorkflowRunner
      │
      ▼
WorkflowRun
      │
      ▼
human-readable CLI evidence
```

The next application boundary is model configuration.

Once users can populate `ModelCatalog` through the installed application, the
complete CLI execution lifecycle can be tested and documented end to end.