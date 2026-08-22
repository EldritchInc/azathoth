# ADR 0054: Add Workflow Inspection Commands

- Status: Accepted
- Date: 2026-08-22

## Context

Azathoth now provides an installed command-line application with a supported
runtime-bootstrap boundary.

Before this decision, the application could start and reconstruct durable
Azathoth configuration, but it exposed no domain operations.

```text
azathoth
   │
   ├── help
   └── version
```

Users therefore could not inspect configured workflows without writing Python
code or directly inspecting persistence.

The first domain commands should exercise the existing application, persistence,
catalog, and runtime boundaries without introducing workflow execution or new
domain semantics.

## Decision

The CLI provides a `workflow` command family beginning with two inspection
operations:

```text
azathoth workflow list
azathoth workflow show <WORKFLOW_ID>
```

These commands inspect durable `WorkflowSpecification` instances.

They do not generate or execute workflow candidates.

## Command Hierarchy

The command-line hierarchy becomes:

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

The `workflow` command establishes the namespace for future workflow
operations.

## Workflow Listing

`workflow list` reconstructs the configured runtime and reads its durable
workflow catalog.

```text
azathoth workflow list
        │
        ▼
CliRuntimeConfiguration
        │
        ▼
load_runtime()
        │
        ▼
AzathothRuntime
        │
        ▼
WorkflowCatalog
        │
        ▼
stdout
```

Each configured workflow is rendered as one line containing:

```text
WORKFLOW_ID  VERSION  NAME
```

For example:

```text
11111111-1111-1111-1111-111111111111  1.0.0  classify sentiment
22222222-2222-2222-2222-222222222222  2.1.0  extract invoice
```

No header or decorative table is emitted.

This keeps the initial output compact and useful with ordinary shell tools.

```bash
azathoth workflow list | grep classify
```

An empty workflow catalog produces no output and exits successfully.

## Workflow Inspection

`workflow show` accepts a workflow UUID.

```text
azathoth workflow show <WORKFLOW_ID>
```

The command loads the corresponding durable workflow specification and renders
human-readable metadata and structural information.

The workflow view includes:

- workflow ID;
- name;
- version;
- description;
- number of steps;
- step IDs;
- step types;
- prompt strategy names;
- tool requirement names and versions;
- dependency counts;
- input counts;
- output counts; and
- condition counts.

The command intentionally presents workflow structure rather than a complete
serialization of every nested domain object.

## Durable Inspection Boundary

Both commands inspect `WorkflowSpecification`.

```text
WorkflowSpecification
        │
        ├── metadata
        └── durable steps
```

They do not resolve:

```text
WorkflowCandidate
```

and they do not execute:

```text
WorkflowRun
```

The boundary is therefore:

```text
workflow list/show
       │
       ▼
durable configuration
```

rather than:

```text
workflow list/show
       │
       ▼
candidate generation
       │
       ▼
provider execution
```

## Prompt and Tool Steps

Workflow inspection distinguishes the two durable workflow-step kinds.

Prompt-backed steps are rendered as:

```text
Type: prompt
Strategy: <strategy name>
```

Tool-backed steps are rendered as:

```text
Type: tool
Tool: <tool requirement name>
Tool Version: <required version>
```

The CLI does not resolve either step to an executable implementation merely to
display it.

## Structural Counts

The human-readable workflow view includes counts for durable structural
bindings.

```text
Dependencies: N
Inputs: N
Outputs: N
Conditions: N
```

The initial view does not serialize the complete contents of these collections.

A future machine-readable output mode may expose complete durable
configuration without making the default terminal representation equivalent to
a raw model dump.

## Workflow Identifiers

`workflow show` parses its identifier as a UUID at the command-line boundary.

Malformed identifiers are therefore argument errors.

```text
azathoth workflow show not-a-uuid
        │
        ▼
argument parser
        │
        ▼
exit 2
```

A syntactically valid UUID that does not identify a configured workflow is a
domain lookup failure.

```text
azathoth workflow show <unknown UUID>
        │
        ▼
workflow catalog
        │
        ▼
not configured
        │
        ▼
exit 1
```

This distinguishes invalid command syntax from a valid request for unavailable
application state.

## Provider Independence

Workflow inspection does not require executable language-model providers.

```text
WorkflowCatalog
      │
      ▼
list / show
```

An OpenRouter API key is therefore not required.

This preserves the distinction between:

```text
durable configuration
```

and:

```text
process-local executability
```

A workflow may refer to requirements that cannot currently be resolved to an
executable candidate and still remain inspectable.

## Runtime Bootstrap

The commands use the supported CLI runtime-bootstrap path.

They do not directly construct workflow repositories or catalog loaders.

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
   │
   ▼
runtime.workflows
```

This ensures domain commands observe the same configured Azathoth environment
rather than creating command-specific reconstruction paths.

## Lazy Command Behavior

Help remains independent from runtime bootstrap.

```text
azathoth workflow --help
        │
        ▼
argument parser
        │
        ▼
help
        │
        ▼
exit
```

It does not create or open the configured database.

Actual inspection commands cross the bootstrap boundary:

```text
azathoth workflow list
        │
        ▼
runtime bootstrap
```

This preserves the application's lazy-startup contract.

## Installed Application Verification

Workflow inspection is verified through the actual installed `azathoth`
console script.

Tests persist durable workflow specifications into a temporary SQLite database,
configure that database through `AZATHOTH_DATABASE`, and execute the installed
application as a subprocess.

```text
temporary SQLite database
        │
        ▼
persist workflows
        │
        ▼
AZATHOTH_DATABASE
        │
        ▼
installed azathoth executable
        │
        ├── workflow list
        └── workflow show
```

This verifies the complete path from durable persistence through application
bootstrap and command rendering.

The tests also verify that inspection succeeds without OpenRouter credentials.

## Workflow Lifecycle

Workflow inspection is only part of the CLI workflow lifecycle.

The intended progression is:

```text
serialized WorkflowSpecification
        │
        ▼
workflow import
        │
        ▼
durable persistence
        │
        ├── workflow list
        ├── workflow show
        │
        ▼
workflow run
```

`workflow import` should precede workflow execution so a fresh CLI user can
populate durable workflow configuration without writing Python code or
manually modifying SQLite state.

## Why Import Precedes Run

Adding `workflow run` immediately after inspection would leave a gap in the
application experience.

The CLI would be able to execute a configured workflow but would provide no
supported CLI-native way to configure one.

That would produce:

```text
external Python or database manipulation
        │
        ▼
workflow run
```

instead of a complete application path:

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

Therefore workflow import is the next workflow capability after inspection.

## Import Versus Interactive Creation

The initial workflow-ingestion command should import a complete serialized
`WorkflowSpecification`.

It should not introduce an interactive workflow builder.

```text
workflow import workflow.json
        │
        ▼
WorkflowSpecification validation
        │
        ▼
existing workflow persistence
```

A command such as `workflow add` would imply a larger authoring surface for
constructing metadata, steps, dependencies, inputs, outputs, conditions,
requirements, and policies from command-line arguments.

That is outside the initial OSS V1 CLI scope.

## Execution Remains Separate

This decision does not introduce:

```text
workflow run
```

Workflow execution crosses additional boundaries:

```text
WorkflowSpecification
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
```

It also introduces executable-provider requirements and execution-result
rendering.

Those concerns should be added after the CLI can ingest its own durable
workflow configuration.

## Consequences

### Positive

- The installed application now exposes real Azathoth domain state.
- Users can list durable workflows without writing Python.
- Users can inspect workflow structure without executing it.
- Inspection requires no provider credentials.
- Commands reuse the existing runtime-bootstrap boundary.
- Empty workflow catalogs have simple successful behavior.
- Invalid UUIDs and unknown workflows have distinct error semantics.
- Installed-console integration is tested end to end.
- The `workflow` namespace is established for subsequent operations.
- The path toward workflow import and execution is explicit.

### Negative

- Workflows cannot yet be imported through the CLI.
- Workflows cannot yet be executed through the CLI.
- Human-readable `show` output does not expose every nested configuration
  field.
- Workflow inspection currently bootstraps the complete configured runtime even
  though it only consumes the workflow catalog.

## Alternatives Considered

### Read Workflow Persistence Directly From Command Handlers

Rejected.

CLI domain commands should consume the established runtime-bootstrap boundary
rather than creating command-specific persistence paths.

### Generate a Workflow Candidate During `show`

Rejected.

Inspection concerns durable configuration.

Candidate generation introduces executable model and tool resolution that is
irrelevant to viewing a workflow specification.

### Require Provider Credentials for Workflow Inspection

Rejected.

Provider credentials affect executability, not the existence of durable
workflow configuration.

### Add `workflow run` Before Workflow Import

Rejected.

That would make execution available before a fresh CLI user had a supported
application path for populating the workflow catalog.

### Add Interactive `workflow add`

Deferred.

Constructing complete workflow specifications through CLI arguments introduces
a substantially larger authoring interface.

Importing an already serialized `WorkflowSpecification` is a smaller and more
faithful initial persistence boundary.

## Result

Azathoth's installed application can now inspect its first durable domain
object.

```text
$ azathoth workflow list

$ azathoth workflow show <WORKFLOW_ID>
```

The application has crossed from:

```text
application shell
```

to:

```text
operable durable state
```

The next workflow capability is ingestion.

```text
workflow.json
      │
      ▼
azathoth workflow import
      │
      ▼
durable workflow catalog
```

Once workflows can enter the application through the CLI, execution can follow.