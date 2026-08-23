# ADR 0055: Support Portable Workflow JSON Import

- Status: Accepted
- Date: 2026-08-23

## Context

Azathoth persists durable `WorkflowSpecification` objects independently from
their executable runtime candidates.

The workflow persistence subsystem already serializes specifications as JSON
and reconstructs them through the workflow domain model.

```text
WorkflowSpecification
        │
        ▼
JSON serialization
        │
        ▼
WorkflowRepository
```

The command-line application can inspect configured workflows through:

```text
azathoth workflow list
azathoth workflow show <WORKFLOW_ID>
```

Before this decision, however, a fresh CLI user still needed Python code or
direct database access to populate the workflow catalog.

The application therefore required a portable workflow-ingestion boundary.

## Decision

Azathoth exposes the existing durable workflow JSON representation as a public
workflow document format.

The workflow subsystem provides:

```text
encode_workflow_document()
decode_workflow_document()
```

and the command-line application provides:

```text
azathoth workflow import <FILE>
```

The imported document represents a complete durable
`WorkflowSpecification`.

## Canonical Document Representation

Workflow documents use the same domain representation that Azathoth already
uses for durable workflow persistence.

```text
WorkflowSpecification
        │
        ▼
encode_workflow_document()
        │
        ▼
JSON document
        │
        ▼
decode_workflow_document()
        │
        ▼
WorkflowSpecification
```

The document format is not a second CLI-specific workflow schema.

It is the portable JSON representation of the existing workflow domain model.

## Encoding

`encode_workflow_document()` serializes a complete
`WorkflowSpecification` as readable indented JSON.

```python
document = encode_workflow_document(specification)
```

The resulting document contains the durable workflow configuration required to
reconstruct the specification.

This includes:

- workflow metadata;
- workflow steps;
- prompt or tool-backed step specifications;
- model requirements;
- dependencies;
- inputs;
- outputs;
- conditions;
- retry policies; and
- failure policies.

Runtime implementations are not serialized.

## Decoding

`decode_workflow_document()` validates JSON through the normal
`WorkflowSpecification` domain model.

```python
specification = decode_workflow_document(document)
```

Malformed JSON, incompatible document structure, and invalid workflow domain
state all produce:

```text
WorkflowDocumentError
```

The original validation exception remains available as the error cause.

This gives consumers a stable workflow-document failure boundary without
requiring them to depend on validation-library exception details.

## Round-Trip Requirement

A workflow document must round-trip through the workflow domain without
changing the durable specification.

```text
WorkflowSpecification
        │
        ▼
encode
        │
        ▼
JSON
        │
        ▼
decode
        │
        ▼
equal WorkflowSpecification
```

Tests cover prompt-backed and tool-backed workflow steps as well as workflow
behavior such as retry and failure policies.

## Checked-In Example

Azathoth includes a canonical importable example:

```text
examples/workflows/simple-prompt.json
```

The example represents a complete prompt-backed workflow specification.

It can be imported directly:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json
```

The example is not approximate schema documentation.

The test suite verifies both that:

```text
decode(example) == expected WorkflowSpecification
```

and that:

```text
example == encode(expected WorkflowSpecification)
```

This makes the checked-in example executable documentation of the current
workflow JSON representation.

## Example Workflow Shape

The simple prompt example demonstrates the essential durable structure:

```text
WorkflowSpecification
├── metadata
│   ├── id
│   ├── name
│   ├── description
│   └── version
│
└── steps
    └── WorkflowStepSpecification
        ├── id
        ├── specification
        │   └── PromptStrategySpec
        │       ├── metadata
        │       ├── prompt
        │       └── model_requirements
        ├── depends_on
        ├── inputs
        ├── outputs
        ├── conditions
        ├── retry_policy
        └── failure_policy
```

The example deliberately uses a prompt-only workflow so a new user can
understand the workflow document format without first configuring durable tool
definitions and implementations.

## CLI Import

The command-line application accepts:

```text
azathoth workflow import <FILE>
```

The command performs:

```text
FILE
 │
 ▼
read UTF-8
 │
 ▼
decode_workflow_document()
 │
 ▼
WorkflowSpecification
 │
 ▼
SQLiteWorkflowRepository.save()
 │
 ▼
durable workflow
```

On success, the CLI prints the imported workflow identifier.

```text
Imported workflow <WORKFLOW_ID>.
```

## Import Does Not Bootstrap Execution

Workflow import is a persistence mutation.

It does not construct an `AzathothRuntime`.

```text
workflow import
      │
      ▼
WorkflowRepository
```

rather than:

```text
workflow import
      │
      ▼
AzathothRuntime
      │
      ▼
candidate generation
```

This preserves the runtime boundary established separately.

The CLI uses its configured database path to construct the existing workflow
repository directly for the persistence operation.

## Provider Independence

Importing a workflow requires no language-model provider credentials.

A workflow document declares durable model requirements.

It does not contain a process-local language-model implementation.

```text
PromptStrategySpec
       │
       ▼
ModelRequirements
```

Concrete executable model resolution occurs later during workflow candidate
generation.

Therefore:

```text
OPENROUTER_API_KEY
```

is unnecessary for:

```text
workflow import
workflow list
workflow show
```

## Validation Before Persistence

The CLI reads and validates the complete workflow document before constructing
the SQLite workflow repository.

```text
read file
    │
    ▼
validate document
    │
    ├── failure → exit
    │
    ▼
construct repository
    │
    ▼
save workflow
```

This means errors such as:

- missing files;
- unreadable files;
- malformed JSON; and
- invalid workflow specifications

fail before the target database is created by the import operation.

## Duplicate Workflows

Workflow persistence retains its existing immutable-insert behavior.

Importing a workflow identifier already present in the configured repository
fails rather than silently replacing durable configuration.

```text
existing workflow ID
        +
imported workflow ID
        │
        ▼
duplicate
        │
        ▼
exit nonzero
```

The CLI surfaces the repository's existing duplicate-workflow error.

## Installed Application Lifecycle

The complete workflow-ingestion lifecycle is tested through the actual
installed `azathoth` console script.

```text
examples/workflows/simple-prompt.json
        │
        ▼
installed azathoth
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

The test executes the same checked-in file that users are instructed to
import.

This verifies the complete path from repository example to persistent
application state.

## CLI Workflow Lifecycle

The workflow CLI now supports:

```text
portable workflow document
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

Workflow execution is the next boundary.

```text
durable workflow
        │
        ▼
workflow run
        │
        ▼
candidate generation
        │
        ▼
WorkflowRunner
```

Import therefore completes the durable half of the CLI workflow lifecycle
before provider-dependent execution is introduced.

## Consequences

### Positive

- Fresh users can populate Azathoth through the installed CLI.
- Workflow interchange uses the existing durable domain representation.
- The CLI introduces no parallel workflow schema.
- Workflow documents are validated through the normal domain model.
- Import requires no provider credentials.
- Invalid documents fail before workflow persistence begins.
- Duplicate workflow identifiers are not silently overwritten.
- A checked-in importable example documents the exact supported JSON shape.
- CI detects when that example becomes stale relative to canonical
  serialization.
- Import, list, and show form a complete terminal-only durable workflow
  lifecycle.

### Negative

- The public workflow document representation is coupled to durable
  `WorkflowSpecification` serialization.
- Schema evolution must therefore consider compatibility with existing workflow
  documents.
- The first example covers only a prompt-backed workflow.
- YAML and other interchange formats are not supported.
- The CLI does not yet export workflows.
- Imported workflows cannot yet be executed from the CLI.

## Alternatives Considered

### Define a Separate CLI Workflow JSON Schema

Rejected.

That would require translation between two representations of the same durable
domain and create an additional compatibility surface.

### Deserialize Directly Inside the CLI

Rejected.

Workflow JSON interchange is a workflow-domain concern and may be useful to
non-CLI consumers.

### Persist Before Complete Validation

Rejected.

Invalid workflow documents should never create partial durable workflow state.

### Add YAML Alongside JSON

Deferred.

JSON is already the representation used by existing workflow persistence and
requires no additional serialization dependency.

### Add Interactive Workflow Creation

Deferred.

Importing a complete durable specification provides a much smaller and more
faithful OSS V1 authoring boundary.

### Add Workflow Execution in the Same Change

Rejected.

Import concerns durable state.

Execution introduces runtime candidate generation, provider executability,
workflow execution, and result rendering.

## Result

Azathoth now has a portable, validated workflow-ingestion path.

```text
workflow JSON
     │
     ▼
domain validation
     │
     ▼
durable persistence
     │
     ├── list
     └── show
```

A user can now take the checked-in example and operate entirely through the
installed application:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json

azathoth workflow list

azathoth workflow show \
    11111111-1111-1111-1111-111111111111
```

The next step is execution.