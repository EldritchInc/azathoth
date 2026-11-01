# Standard Tools

`azathoth.standard` is the tool library that ships inside the Azathoth
package (ADR 0095). Its documents are ordinary tool documents, stored in
`tools/`, and are recorded in a database the same way as any other tool: by
an explicit import of each exact tool version.

The library holds two kinds of tool. The composition tools run other
workflows, and the data-shaping tools reshape the values that pass between
steps:

| Tool              | Version | Implementation | Purpose                                     |
| ----------------- | ------- | -------------- | ------------------------------------------- |
| `run_workflow`    | 1.0.0   | 1.0.3          | Run a child workflow once (ADR 0084).       |
| `loop_workflow`   | 1.1.0   | 1.1.3          | Run a child workflow repeatedly (ADR 0090). |
| `json_select`     | 1.0.0   | 1.0.0          | Select one value from JSON by path.         |
| `json_object`     | 1.0.0   | 1.0.0          | Build one object from a step's inputs.      |
| `json_merge`      | 1.0.0   | 1.0.0          | Deep-merge one object into another.         |
| `validate_json`   | 1.0.0   | 1.0.0          | Check a value against a JSON Schema.        |
| `chunk_text`      | 1.0.0   | 1.0.0          | Split text into chunks of a size.           |
| `join_text`       | 1.0.0   | 1.0.0          | Join strings, or rendered objects.          |
| `render_template` | 1.0.0   | 1.0.0          | Render a text template from inputs.         |

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
into one object, lay defaults under a request, check that a reply has the
shape the next step needs, split a long text, or put a document together. Each one is a process
tool that runs its source with `python`, like the composition tools, but:

- it grants itself no variables, so it sees only the base environment;
- its source never imports Azathoth, so what it does is fixed by its
  recorded document, not by the Azathoth version that happens to be
  installed. It uses only the Python standard library, except that
  `validate_json` also uses `jsonschema`, which Azathoth itself requires;
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

| Input     | Required | Meaning                                          |
| --------- | -------- | ------------------------------------------------ |
| `value`   | yes      | Any JSON value                                   |
| `path`    | yes      | A list of object keys (strings) and list indexes |
| `default` | no       | The result when nothing is at `path`             |

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

### validate_json

`validate_json` checks `value` against the JSON Schema `schema` and returns
the value unchanged, as `value`:

| Input    | Required | Meaning                               |
| -------- | -------- | ------------------------------------- |
| `value`  | yes      | Any JSON value                        |
| `schema` | yes      | A JSON Schema: an object or a boolean |

A model's JSON reply is parsed, not checked: a reply that leaves out a field
reaches the next step without it. Placed after the model's step, with the
schema as a constant, `validate_json` stops the run there instead, and the
steps after it read the checked value from its output:

```json
{
  "specification": {"requirement": {"name": "validate_json", "version": "1.0.0", "runtime": "process"}},
  "inputs": [
    {"name": "value", "source": {"producer_step_id": "<PLAN STEP ID>", "name": "story"}},
    {"name": "schema", "source": {"value": {"type": "object", "required": ["title", "characters"]}}}
  ],
  "outputs": [{"name": "story", "path": ["value"]}]
}
```

The schema's dialect follows its `$schema` keyword and defaults to Draft
2020-12, as for benchmark schemas. `format` is an annotation, as Draft
2020-12 defines it, and is not checked. A schema refers only to itself:
`$ref` reaches its own `$defs`, and nothing is fetched from the network.

A value that does not match fails with status 1. The message names the
first violation, ordered by JSON path and then by message, and counts the
others:

```text
validate_json rejected the value at $.characters[0]: 'name' is a required property.
validate_json rejected the value at $: 'title' is a required property (and 2 more errors).
```

A violation's message is cut at 300 characters, because it can quote the
value, and a long chapter would push the start of the message out of what
the engine quotes.

A schema that is not one fails with status 2 before any value is checked, as
does a reference the schema cannot resolve:

```text
validate_json needs 'schema' to be a JSON Schema: an object or a boolean.
validate_json was given an invalid schema: 'nope' is not valid under any of the given schemas.
validate_json could not resolve a reference in the schema: Unresolvable: https://example.com/story.json.
```

`validate_json` runs `jsonschema` from the `python` that runs it. That is
Azathoth's own Python when Azathoth's environment is active, as in the
container. Any other Python fails with status 2:

```text
validate_json needs the jsonschema package, which Azathoth installs; run it with the Python that runs Azathoth.
```

### Templates

`render_template` and `join_text` fill templates the way prompt templates
are filled, so one template language covers prompts and text:

- `{name}` is replaced by the value called `name`; `{{` and `}}` are literal
  braces.
- A string is inserted as it is. Any other value is inserted as compact JSON,
  exactly as a prompt renders it: `{"title":"The Keeper"}`, `3`, `true`,
  `null`.
- Only plain names are placeholders. Fields, indexes, conversions and
  format specifications, such as `{story.title}`, `{chapters[0]}`, `{n!r}`
  or `{n:>3}`, fail with status 2; select a nested value with `json_select`
  first.

### chunk_text

`chunk_text` splits `text` into `chunks`, each at most `max_characters`
characters long:

| Input                | Required | Meaning                                        |
| -------------------- | -------- | ---------------------------------------------- |
| `text`               | yes      | The text to split                              |
| `max_characters`     | yes      | The most characters in one chunk, at least 1   |
| `overlap_characters` | no       | How far a chunk reaches back into the last one |

Characters are Unicode code points. No tokenizer is involved, so how many
tokens a chunk is depends on the model that reads it; leave room for that
when choosing `max_characters`.

Each chunk ends at the last boundary in the second half of its allowed
length, in this order of preference: a paragraph break, a line break, the
end of a sentence, any whitespace. A chunk with none of these is cut at
exactly `max_characters`. The boundary stays at the end of the chunk before
it, so without overlap `join_text` with an empty `separator` gives back the
text exactly. Empty text gives no chunks.

With `overlap_characters`, each chunk starts that many characters before the
previous one ended, by characters and not at a boundary, so a chunk can
start inside a word. A chunk always starts after the one before it.

`max_characters` must be a whole number of at least 1, and
`overlap_characters` a whole number from 0 to one less than
`max_characters`; anything else fails with status 2:

```text
chunk_text needs 'max_characters' to be a whole number of at least 1.
chunk_text needs 'overlap_characters' to be a whole number from 0 to one less than 'max_characters'.
```

### join_text

`join_text` joins `items` into one `text`:

| Input           | Required | Meaning                                             |
| --------------- | -------- | --------------------------------------------------- |
| `items`         | yes      | An array of strings, or of objects with a template  |
| `separator`     | no       | What goes between items; two line breaks by default |
| `item_template` | no       | A template each object is rendered through          |

Without `item_template`, every item must be a string. With it, every item
must be an object, and each is rendered from its own fields. This renders a
book's chapters:

```json
{"name": "item_template", "source": {"value": "## Chapter {number}: {title}\n\n{text}"}}
```

An item that is the wrong kind fails with status 2, and an object that lacks
a field the template names fails with status 1, naming the item by its JSON
path:

```text
join_text joins strings, or objects through an item_template; item $[1] is an object.
join_text found no value for {title} in item $[2].
```

### render_template

`render_template` renders `template` from the step's other inputs into
`text`. Every input other than `template` is a value the template may use,
and the ones it does not use are ignored. This step puts a book together:

```json
{
  "specification": {"requirement": {"name": "render_template", "version": "1.0.0", "runtime": "process"}},
  "inputs": [
    {"name": "template", "source": {"value": "# {title}\n\n{chapters}\n"}},
    {"name": "title", "source": {"producer_step_id": "<PLAN STEP ID>", "name": "title"}},
    {"name": "chapters", "source": {"producer_step_id": "<JOIN STEP ID>", "name": "text"}}
  ],
  "outputs": [{"name": "markdown", "path": ["text"]}]
}
```

A placeholder with no input of its name fails with status 2, and so does a
template that is not one:

```text
render_template has no value for {title}.
render_template allows only plain {name} placeholders; {story.title} is not one.
render_template could not read the template: Single '}' encountered in format string.
render_template reserves the name 'template' for the template itself.
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
Installed tool validate_json@1.0.0 revision 1.
Installed tool chunk_text@1.0.0 revision 1.
Installed tool join_text@1.0.0 revision 1.
Installed tool render_template@1.0.0 revision 1.
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
