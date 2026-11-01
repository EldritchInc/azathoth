# Standard Tools

`azathoth.standard` is the tool library that ships inside the Azathoth
package (ADR 0095). Its documents are ordinary tool documents, stored in
`tools/`, and are recorded in a database the same way as any other tool: by
an explicit import of each exact tool version.

The library holds two kinds of tool. The composition tools run other
workflows, and the data-shaping tools reshape the values that pass between
steps:

| Tool            | Version | Implementation | Purpose                                     |
| --------------- | ------- | -------------- | ------------------------------------------- |
| `run_workflow`  | 1.0.0   | 1.0.3          | Run a child workflow once (ADR 0084).       |
| `loop_workflow` | 1.1.0   | 1.1.3          | Run a child workflow repeatedly (ADR 0090). |
| `json_select`   | 1.0.0   | 1.0.0          | Select one value from JSON by path.         |
| `json_object`   | 1.0.0   | 1.0.0          | Build one object from a step's inputs.      |
| `json_merge`    | 1.0.0   | 1.0.0          | Deep-merge one object into another.         |

`standard_tool_documents()` decodes them in that fixed order:

```python
from azathoth.standard import standard_tool_documents

for document in standard_tool_documents():
    print(document.definition.name, document.definition.version)
```

## The Composition Tools

`run_workflow` and `loop_workflow` run `azathoth workflow invoke` in a child
process, so both grant themselves the variables it needs (ADR 0099), the
tracing configuration it needs to continue a trace (ADR 0100), and the
Bedrock configuration and AWS credentials it needs to run Bedrock models
(ADR 0103):

```json
"environment": [
  "AZATHOTH_DATABASE",
  "OPENROUTER_API_KEY",
  "AZATHOTH_WORKFLOW_DEPTH",
  "AZATHOTH_OTEL",
  "OTEL_*",
  "AZATHOTH_BEDROCK",
  "AZATHOTH_BEDROCK_PRICING",
  "AWS_*"
]
```

No other variable outside the base environment reaches them. When their step
is traced, the engine also gives them its `TRACEPARENT`, which they pass on
to the child.

## The Data-Shaping Tools

The data-shaping tools turn one step's output into the next step's input:
they pick a field out of a model's reply, gather values from several steps
into one object, or lay defaults under a request. Each one is a process
tool that runs its source with `python`, like the composition tools, but:

- it grants itself no variables, so it sees only the base environment;
- its source uses only the Python standard library and never imports
  Azathoth, so what it does is fixed by its recorded document, not by the
  Azathoth version that happens to be installed;
- it has a 60-second timeout;
- its result is one JSON object, which the step's output bindings read by
  path, like any tool's.

Every input is bound by name, and any of them can be a constant (ADR 0094).
A tool fails rather than guess. A tool given an input it does not take, or
missing one it needs, or given an input of the wrong shape, exits with status
2; a tool whose data does not hold what the step asked for exits with status
1. The step's error carries the tool's own message:

```text
Tool implementation <ID> exited with status <N>: <MESSAGE>
```

The engine quotes at most the last 500 characters of a tool's error output,
so every message is written to fit.

### json_select

`json_select` returns the value at `path` inside `value`, as `value`:

| Input     | Required | Meaning                                              |
| --------- | -------- | ---------------------------------------------------- |
| `value`   | yes      | Any JSON value                                       |
| `path`    | yes      | A list of object keys (strings) and list indexes     |
| `default` | no       | The result when nothing is at `path`                 |

A path reads exactly like an output binding's: a string is an object key,
and an integer is a list index, counting from the end when negative. An
empty path selects the whole value. This step reads a request's
`max_chapters`, or 18 when the request has none:

```json
{
  "specification": {"requirement": {"name": "json_select", "version": "1.0.0", "runtime": "process"}},
  "inputs": [
    {"name": "value", "source": {"event_type": "workflow.input.received", "field_name": "input"}},
    {"name": "path", "source": {"value": ["max_chapters"]}},
    {"name": "default", "source": {"value": 18}}
  ],
  "outputs": [{"name": "max_chapters", "path": ["value"]}]
}
```

`default` is used only when nothing is at the path. A `null` at the path is
a value, so it is returned as it is. Without a default, a path that holds
nothing fails with status 1, saying where it stopped:

```text
json_select found no value at path ["story", "title"]: missing object key 'title'.
json_select found no value at path ["chapters", 0]: expected a list for index 0.
json_select found no value at path ["chapters", 2]: list index 2 is out of range.
```

A `path` that is not a list of strings and integers fails with status 2:

```text
json_select needs 'path' to be a list of object keys and list indexes.
```

### json_object

`json_object` returns one object, as `value`, whose fields are the step's
inputs, in the order the step declares them. A step input binds one source,
so this is how a step gathers values from several earlier steps, constants
and the workflow input:

```json
{
  "specification": {"requirement": {"name": "json_object", "version": "1.0.0", "runtime": "process"}},
  "inputs": [
    {"name": "title", "source": {"producer_step_id": "<PLAN STEP ID>", "name": "title"}},
    {"name": "chapters", "source": {"producer_step_id": "<WRITE STEP ID>", "name": "chapters"}},
    {"name": "edition", "source": {"value": 1}}
  ],
  "outputs": [{"name": "book", "path": ["value"]}]
}
```

It takes any inputs, and a step with none builds `{}`. It never fails on
its inputs.

### json_merge

`json_merge` merges `patch` into `base` and returns the merged object as
`value`:

| Input   | Required | Meaning                  |
| ------- | -------- | ------------------------ |
| `base`  | yes      | The object to start from |
| `patch` | yes      | The object laid over it  |

Where both hold an object under the same key, the two objects merge the same
way, recursively. Any other value in `patch` replaces the one in `base`:

```text
base   {"settings": {"max_chapters": 18, "timeout": 1800}, "tags": ["a", "b"], "ending": "open"}
patch  {"settings": {"max_chapters": 3}, "tags": ["c"], "ending": null}
value  {"settings": {"max_chapters": 3, "timeout": 1800}, "tags": ["c"], "ending": null}
```

Arrays are replaced, never concatenated. A `null` in `patch` is kept as a
value; it does not delete the field, as a JSON Merge Patch (RFC 7396) would.
So a constant `base` of defaults with the request as `patch` gives the
request with every default it left out.

Both inputs must be objects. Anything else fails with status 2:

```text
json_merge can only merge objects; patch is an array.
```

## Installing

The library reaches a database through the CLI:

```bash
azathoth init
azathoth tool install-standard
```

`init` creates the database if needed and then installs the library;
`tool install-standard` installs it into an existing one. Each document is
compared by content digest with the latest revision of its exact tool
version: a missing version is imported, an identical one is left alone, and
a differing one gets the standard document as its next revision. The CLI
reference describes the output.

## Changing a standard tool

A standard tool is never changed in place. A change ships as a new tool
version with a new implementation ID, because an implementation ID belongs to
one tool version only, and workflows keep requiring the exact versions they
name.

There has been one exception, made three times in 1.1. When process tools stopped
inheriting Azathoth's environment (ADR 0099), `run_workflow@1.0.0` and
`loop_workflow@1.1.0` gained their grants as the next revision of the same
versions, implementations 1.0.1 and 1.1.1, because without grants no
existing workflow could run a child at all. When tracing arrived (ADR 0100),
they gained `AZATHOTH_OTEL` and `OTEL_*` the same way, as implementations
1.0.2 and 1.1.2, so a child continues its parent's trace. When Bedrock
arrived (ADR 0103), they gained `AZATHOTH_BEDROCK`, `AZATHOTH_BEDROCK_PRICING`
and `AWS_*` the same way, as implementations 1.0.3 and 1.1.3, so a child
runs Bedrock models with its parent's region, prices and credentials.

A database that installed the library from Azathoth 1.0 runs
`azathoth tool install-standard`, or `azathoth init`, once to pick up the
current revisions. The same run installs the data-shaping tools, which are
new in 1.1:

```text
Installed tool run_workflow@1.0.0 revision 2.
Installed tool loop_workflow@1.1.0 revision 2.
Installed tool json_select@1.0.0 revision 1.
Installed tool json_object@1.0.0 revision 1.
Installed tool json_merge@1.0.0 revision 1.
```

A database that already holds implementations 1.0.1 and 1.1.1 gets 1.0.3 and
1.1.3 as revision 3 the same way, and one that holds 1.0.2 and 1.1.2 gets
them as revision 4.

A tool belongs here when it is pure Python, deterministic, works on Windows,
needs no network, and has no side effects outside its inputs. The
composition tools are the one exception: their side effects are Azathoth's
own recorded invocations and runs. The data-shaping tools take their
identifiers from the `c2000000-…` range, and no example tool may share an
identifier with a standard tool.
