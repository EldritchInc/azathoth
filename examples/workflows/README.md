# Workflow Examples

This directory contains complete JSON representations of durable Azathoth
`WorkflowSpecification` objects.

The files are directly importable by the command-line application.

## Simple Prompt Workflow

Import the basic prompt-backed example:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json
```

Then list configured workflows:

```bash
azathoth workflow list
```

The imported workflow appears as:

```text
11111111-1111-1111-1111-111111111111  1.0.0  simple prompt
```

Inspect the complete workflow structure:

```bash
azathoth workflow show \
    11111111-1111-1111-1111-111111111111
```

## JSON Document Format

Workflow JSON files use the canonical serialized representation of
`WorkflowSpecification`.

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

The checked-in examples are validated in the test suite against Azathoth's
actual workflow models.

They are therefore executable examples rather than approximate schema
documentation.

## Provider Configuration

Importing and inspecting a workflow does not require provider credentials.

The example declares model requirements rather than binding the prompt step to
a specific executable language model.

Concrete model resolution occurs later during workflow candidate generation.