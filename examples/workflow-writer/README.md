# Workflow Writer Example

`write-workflow.json` is a workflow that writes workflows. Given a
plain-English request, it drafts an Azathoth workflow document, validates it
with Azathoth's own workflow model, and repairs it once from the validator's
errors when it is invalid.

```text
draft ──► validate ──► invalid? ──► repair ──► validate again
                  │                                  │
                  └──────────────► finalize ◄────────┘
```

| Document | ID |
| --- | --- |
| `workflows/write-workflow.json` | `a2000000-0000-4000-8000-000000000010` |
| `tools/validate-workflow.json` | `a2000000-0000-4000-8000-000000000001` |
| `tools/finalize-workflow.json` | `a2000000-0000-4000-8000-000000000002` |
| `benchmarks/write-workflow.json` | `a2000000-0000-4000-8000-000000000030` |

## The Validator

`validate_workflow` is a process tool. It runs `python`, imports
`azathoth.workflows`, and checks the draft against `WorkflowSpecification`,
exactly as `workflow import` would. It never fails: an invalid draft is a
result, so the workflow can act on it.

A valid draft comes back in its canonical encoding. An invalid one comes back
unchanged, with one line per problem:

```text
- metadata: Field required
- steps: Tuple should have at least 1 item after validation, not 0
```

Because it imports Azathoth, the validator needs Azathoth's own environment
to be the active one, so that `python` is the interpreter Azathoth is
installed in.

## The Prompts

The draft prompt shows the model one complete, valid workflow document and
the rules for writing one. The test suite pulls that example back out of the
prompt and decodes it, so it cannot drift out of date as the workflow model
changes.

The repair prompt shows the same example and rules, the original request,
the rejected draft, and the validator's errors.

Both prompts declare `"output_format": "json"`, so their replies are parsed
as JSON before the validator sees them (ADR 0088).

## One Repair, Not a Loop

The repair and its validation run only when the first validation failed.
`finalize` reads `valid`, `errors` and `checked` by name, and the second
validation is declared before the first, so its answer wins whenever it ran
(ADR 0080).

One bounded pass is enough for most drafts. To keep repairing until the
draft is valid, move repair and validation into a loop body for the
`loop_workflow` tool (ADR 0090), with state `{request, document, errors}`,
done when the validator says the document is valid.

## Running It

With a provider configured and models authorized (see the CLI README):

```bash
azathoth tool import examples/workflow-writer/tools/validate-workflow.json
azathoth tool import examples/workflow-writer/tools/finalize-workflow.json

azathoth workflow import examples/workflow-writer/workflows/write-workflow.json

azathoth workflow run a2000000-0000-4000-8000-000000000010 \
    --input '"Classify a customer review as positive or negative."' \
    --output result > written.json
```

The result says whether the workflow is valid, why not, and the workflow:

```json
{"valid": true, "errors": "", "workflow": {"metadata": {...}, "steps": [...], "result": {...}}}
```

A valid workflow can be imported directly:

```bash
python -c "import json; print(json.dumps(json.load(open('written.json'))['workflow'], indent=2))" > workflow.json

azathoth workflow import workflow.json
```

Validity is structural. A valid workflow can still name a tool that is not
imported, or require a model that is not authorized. Those are found when it
runs, as with any workflow.

## Benchmark

`benchmarks/write-workflow.json` holds two schema cases, which require a
valid workflow with no errors, and two semantic cases, which judge whether
the workflow does what was asked. Schema cases need no judge; semantic cases
do:

```bash
azathoth judge add <MODEL_IDENTIFIER>
azathoth benchmark import examples/workflow-writer/benchmarks/write-workflow.json
```
