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

## Workflow Commands

The current workflow command family is:

```text
azathoth workflow
├── import <FILE>
├── list
└── show <WORKFLOW_ID>
```

### Import a Workflow

Import a complete durable workflow JSON document:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json
```

On success:

```text
Imported workflow 11111111-1111-1111-1111-111111111111.
```

The command:

```text
FILE
 │
 ▼
workflow JSON validation
 │
 ▼
WorkflowSpecification
 │
 ▼
SQLiteWorkflowRepository
```

Import does not require provider credentials or runtime candidate generation.

### Example JSON

The canonical example is:

```text
examples/workflows/simple-prompt.json
```

It is a complete JSON representation of a `WorkflowSpecification`, not a
simplified tutorial schema.

Its high-level structure is:

```text
{
  metadata,
  steps: [
    {
      id,
      specification: {
        metadata,
        prompt,
        model_requirements
      },
      depends_on,
      inputs,
      outputs,
      conditions,
      retry_policy,
      failure_policy
    }
  ]
}
```

The actual checked-in file should be used as the authoritative example.

CI verifies that it exactly matches Azathoth's canonical workflow
serialization.

### List Workflows

```bash
azathoth workflow list
```

Each configured workflow is rendered as:

```text
WORKFLOW_ID  VERSION  NAME
```

### Inspect a Workflow

```bash
azathoth workflow show <WORKFLOW_ID>
```

This displays durable workflow metadata and step topology without generating or
executing a workflow candidate.

## Current Workflow Lifecycle

The CLI can now complete the durable workflow lifecycle without Python code.

```text
JSON file
    │
    ▼
workflow import
    │
    ▼
SQLite
    │
    ├── workflow list
    └── workflow show
```

The next workflow command crosses into execution:

```text
workflow run
      │
      ▼
candidate generation
      │
      ▼
WorkflowRunner
```

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