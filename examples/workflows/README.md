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

The process tool runs `python`, so it needs `python` on the `PATH`. An activated
virtual environment provides it on macOS, Linux and Windows alike. Neither step
calls a language model, so no provider credentials are needed.

## Word Count With Step Messages

`word-count-messages.json` is the redundant word count with step messages.
Each step announces itself as it starts, and the process step also emits its
count as soon as it succeeds:

```json
"message": "Counting words with the process tool",
"emit_values": true
```

The Python step declares a message only, so it announces itself but emits no
values.

Import both tools as above, then import and promote the workflow:

```bash
azathoth workflow import \
    examples/workflows/word-count-messages.json

azathoth workflow promote \
    a1000000-0000-4000-8000-000000000002
```

Invoking it streams JSON Lines by default:

```bash
azathoth workflow invoke \
    a1000000-0000-4000-8000-000000000002 \
    --input '"the old ones wait"'
```

```text
{"type": "step", "step_id": "a1000000-0000-4000-8000-000000000021", "message": "Counting words with the process tool"}
{"type": "step", "step_id": "a1000000-0000-4000-8000-000000000022", "message": "Counting words with the Python tool"}
{"type": "output", "step_id": "a1000000-0000-4000-8000-000000000021", "values": {"count": 4}}
{"type": "result", "invocation_id": "<INVOCATION_ID>", "value": {"result": 4}}
```

If the process tool fails, its `output` record never appears, and the
invocation still succeeds with the Python tool's count, because the run
completed. Add `--output result` to print only `{"result": 4}`.

The workflow can also run without promotion, with `workflow run --input`.
`examples/benchmarks/word-count.json` holds one exact case for it, and the
CLI README walks through turning a miscounted run into a second case with
`benchmark add-case`.

## Running a Child Workflow

`count-words-in-child.json` counts words by invoking another workflow as a
child. Its one step uses the `run_workflow` tool from
`examples/tools/run-workflow.json`, a process tool that runs:

```bash
azathoth workflow invoke <CHILD_WORKFLOW_ID> --input <JSON> --output jsonl
```

as a separate process and returns the child's result. Only the child's final
record reaches the parent: its result value on success, or its error message
and invocation ID on failure. The child's step records stay in the child.

Because the child is invoked, it runs its promoted production state, so it
must be promoted first. The caller names the child and its input:

```json
{"workflow_id": "<CHILD_WORKFLOW_ID>", "input": <CHILD_INPUT>}
```

Import the three tools and both workflows, promote the child, then run the
parent:

```bash
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth tool import examples/tools/run-workflow.json

azathoth workflow import examples/workflows/word-count-messages.json
azathoth workflow import examples/workflows/count-words-in-child.json

azathoth workflow promote a1000000-0000-4000-8000-000000000002

azathoth workflow run a1000000-0000-4000-8000-000000000003 \
    --input '{"workflow_id": "a1000000-0000-4000-8000-000000000002", "input": "the old ones wait — and dream"}' \
    --output result
```

```text
7
```

Without the promotion, the parent's step fails and the run halts:

```text
Tool implementation c1000000-0000-4000-8000-000000000011 exited with status 1: Child workflow a1000000-0000-4000-8000-000000000002 invocation <INVOCATION_ID> failed: The requested workflow is not deployed to production.
```

A production invocation reports a generic failure to its caller. To see why a
child failed, follow its invocation to its run:

```bash
azathoth invocation show <INVOCATION_ID>
azathoth run show <RUN_ID>
```

The tool runs the child with its own Python interpreter
(`python -m azathoth.cli`), so it does not depend on `azathoth` being on the
`PATH`. The child inherits the parent's environment, including
`AZATHOTH_DATABASE`, so both use the same database.

Two guards keep children bounded:

- The tool passes `AZATHOTH_WORKFLOW_DEPTH`, plus one, to each child, and
  refuses to go deeper than 8 levels:

  ```text
  Child workflow depth 9 exceeds the limit of 8.
  ```

- The tool stops a child after 55 seconds, inside its own 60-second timeout,
  so a slow child is not left running after the tool itself is stopped.

The depth guard belongs to this example tool, not to Azathoth. Recording a
child's lineage and depth in its initial context is planned after 1.0, along
with constant step inputs that would let a parent name its child itself.

## Looping Over a Child Workflow

A workflow is a graph, so no step runs twice in one run. To repeat work, a
tool invokes a child workflow over and over, one invocation per iteration
(ADR 0090). `examples/tools/loop-workflow.json` is that tool.

Each iteration, the child receives the current state and its iteration
number, and returns the next state, whether it is done, and optionally one
item to collect:

```text
child input   {"state": <state>, "iteration": <n>}
child result  {"state": <next state>, "done": <bool>, "item": <value>}
```

The loop's settings name the child, the iteration limit and the starting
state:

```json
{"workflow_id": "<CHILD_WORKFLOW_ID>", "max_iterations": 10, "state": <STATE>}
```

Two optional settings bound its time: `budget_seconds` for the whole loop and
`child_timeout_seconds` for each iteration.

It returns every item collected, in order, with the final state:

```json
{"items": [...], "state": <STATE>, "iterations": 3, "completed": true}
```

The loop stops when the child says it is done, or after `max_iterations`
iterations. Reaching the limit is not a failure: `completed` is `false`.

`countdown.json` is the smallest possible loop body. It counts its state's
`remaining` number down by one, collects the number it counted, and is done
at zero. `loop-countdown.json` loops over it.

Import the tools and workflows, promote the child, then run the loop:

```bash
azathoth tool import examples/tools/countdown-step.json
azathoth tool import examples/tools/loop-workflow.json

azathoth workflow import examples/workflows/countdown.json
azathoth workflow import examples/workflows/loop-countdown.json

azathoth workflow promote a1000000-0000-4000-8000-000000000004

azathoth workflow run a1000000-0000-4000-8000-000000000005 \
    --input '{"workflow_id": "a1000000-0000-4000-8000-000000000004", "max_iterations": 10, "state": {"remaining": 3}}' \
    --output result
```

```text
[3, 2, 1]
```

With `"max_iterations": 2`, the loop stops early and returns `[3, 2]`.

A failing iteration fails the loop, naming the iteration and the child's
invocation, so it can be followed with `invocation show`:

```text
Iteration 2: child workflow <CHILD_WORKFLOW_ID> invocation <INVOCATION_ID> failed: <MESSAGE>
```

The loop is bounded three ways:

- `max_iterations`, which must be a positive integer;
- time: the loop keeps to `budget_seconds`, stopping each child after
  `child_timeout_seconds` (default 600) or when the budget runs out,
  whichever comes first. The budget defaults to 7140 seconds, just under 2
  hours. A longer one may be set, up to the tool's 24-hour timeout less a
  minute; the loop reads that timeout from `AZATHOTH_TOOL_TIMEOUT_SECONDS`,
  which Azathoth sets for every process tool (ADR 0093). A budget it cannot
  honor fails the loop before any child runs:

  ```text
  Loop budget of 90000 seconds exceeds the tool's timeout of 86400 seconds less a 60-second margin.
  ```

- depth: loops can nest, and each level counts against the same 8-level
  limit as `run_workflow`.

Every iteration is a production invocation with its own run, so each one can
be inspected, and the loop body can be benchmarked, optimized and promoted on
its own. Like `run_workflow`, the loop runs children with its own Python
interpreter, so Azathoth's environment must be the one that is active.

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
