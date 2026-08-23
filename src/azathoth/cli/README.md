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

### Run a Workflow

Execute one configured workflow:

```bash
azathoth workflow run <WORKFLOW_ID>
```

Execution follows the existing runtime and workflow boundaries:

```text
WORKFLOW_ID
    │
    ▼
CLI runtime bootstrap
    │
    ▼
AzathothRuntime
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

A successful run returns exit status `0`.

A completed run containing failed steps is still rendered as execution evidence
and returns exit status `1`.

Failures that prevent candidate generation also return a nonzero status.

### Execution Output

Completed workflow runs are rendered from recorded domain evidence.

The workflow summary includes:

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

Each step includes its ID, status, and attempt count.

Executed steps may additionally include:

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

Optional metrics are omitted when they were not recorded.

Failed steps show the terminal recorded exception type and message.

### Output Values

Strategy outputs are JSON-compatible and are rendered as JSON.

A textual result appears as:

```text
Output:
"success"
```

A structured result appears as:

```text
Output:
{
  "classification": "positive"
}
```

### Model Requirements

Running a prompt-backed workflow requires compatible durable model metadata and
an executable language-model implementation.

For OpenRouter:

```text
persisted ModelMetadata
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

The workflow itself declares `ModelRequirements`.

The CLI does not select one global model for an entire workflow.

### Current Workflow Surface

```text
azathoth workflow
├── import <FILE>
├── list
├── run <WORKFLOW_ID>
└── show <WORKFLOW_ID>
```

The durable and executable workflow boundaries now exist.

The remaining fresh-user execution gap is model configuration.

The planned next application surface is:

```text
azathoth model import <FILE>
azathoth model list
azathoth model show <MODEL_IDENTIFIER>
```

After model configuration is available through the CLI, the installed
application can support a complete end-to-end workflow execution journey
without Python-side database setup.

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