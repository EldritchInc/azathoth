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

## Redundant Word Count Workflow

`redundant-word-count.json` counts words twice in one concurrent layer: once
with the process tool in `examples/tools/word-count-process.json` and once
with the Python tool in `examples/tools/word-count.json`.

Both steps use the `continue` failure policy, and the workflow's result names
the `count` value alone:

```json
"result": {
  "name": "count"
}
```

So the answer comes from the first step, in step order, that succeeded. If the
process tool fails, the Python tool's count is still the result.

Import both tools, then the workflow:

```bash
azathoth tool import \
    examples/tools/word-count-process.json

azathoth tool import \
    examples/tools/word-count.json

azathoth workflow import \
    examples/workflows/redundant-word-count.json
```

Verify the process tool against its test cases:

```bash
azathoth tool verify \
    55555555-5555-5555-5555-555555555555 \
    --version 1.0.0
```

The process tool needs `python3` on the `PATH`. Neither step calls a language
model, so no provider credentials are needed.

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
