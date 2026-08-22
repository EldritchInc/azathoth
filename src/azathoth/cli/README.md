# Command-Line Interface

`azathoth.cli` provides the installed Azathoth command-line application,
runtime bootstrap, and application-facing domain commands.

## Application

Installing Azathoth exposes:

```text
azathoth
```

The package also supports:

```text
python -m azathoth.cli
```

The base application provides:

```bash
azathoth
azathoth --help
azathoth --version
```

Running `azathoth` without arguments displays help.

## Command Structure

The current command hierarchy is:

```text
azathoth
│
├── --help
├── --version
│
└── workflow
    ├── list
    └── show <WORKFLOW_ID>
```

## Workflow Listing

List configured durable workflows with:

```bash
azathoth workflow list
```

Each workflow is rendered as:

```text
WORKFLOW_ID  VERSION  NAME
```

For example:

```text
11111111-1111-1111-1111-111111111111  1.0.0  classify sentiment
```

An empty workflow catalog produces no output and exits successfully.

## Workflow Inspection

Inspect one durable workflow with:

```bash
azathoth workflow show <WORKFLOW_ID>
```

The human-readable view includes workflow metadata and structural information
about each step.

```text
ID: 11111111-1111-1111-1111-111111111111
Name: classify sentiment
Version: 1.0.0
Description: Classify sentiment for one request.
Steps: 1

Step 1
ID: 22222222-2222-2222-2222-222222222222
Type: prompt
Strategy: classify sentiment prompt
Dependencies: 0
Inputs: 0
Outputs: 0
Conditions: 0
```

Prompt and tool-backed steps are identified without resolving them to runtime
implementations.

## Inspection Versus Execution

Workflow inspection operates on durable `WorkflowSpecification` instances.

```text
workflow list / show
        │
        ▼
WorkflowSpecification
```

It does not generate a `WorkflowCandidate` or execute a `WorkflowRun`.

Provider credentials are therefore unnecessary for workflow inspection.

## Runtime Bootstrap

Domain commands reconstruct application state through the supported CLI
bootstrap path.

```text
command
   │
   ▼
CliRuntimeConfiguration
   │
   ▼
load_runtime()
   │
   ▼
AzathothRuntime
```

Commands do not construct their own persistence or provider environments.

## Configuration

The initial runtime configuration recognizes:

```text
AZATHOTH_DATABASE
OPENROUTER_API_KEY
```

`AZATHOTH_DATABASE` selects the SQLite database containing durable application
configuration.

When absent, the default path is:

```text
azathoth.db
```

`OPENROUTER_API_KEY` supplies process-local OpenRouter credentials.

Workflow inspection does not require this credential.

## Lazy Bootstrap

Shell-only operations remain independent from runtime state.

```text
azathoth --help
azathoth --version
azathoth workflow --help
```

do not require runtime bootstrap.

Commands that inspect application state do:

```text
azathoth workflow list
azathoth workflow show <WORKFLOW_ID>
```

## Workflow Lifecycle

The CLI workflow surface is being introduced in lifecycle order.

```text
workflow specification
        │
        ▼
workflow import
        │
        ▼
workflow list / show
        │
        ▼
workflow run
```

Inspection is currently implemented.

The next workflow capability is import of a serialized
`WorkflowSpecification`.

Execution follows after workflows can be ingested through the CLI itself.

## Current Scope

Implemented:

```text
azathoth
azathoth --help
azathoth --version
azathoth workflow list
azathoth workflow show <WORKFLOW_ID>
```

Planned next:

```text
azathoth workflow import <FILE>
azathoth workflow run <WORKFLOW_ID>
```

Benchmark and optimization command families build on the same application and
runtime boundaries afterward.