# Standard Tools

`azathoth.standard` is the tool library that ships inside the Azathoth
package (ADR 0095). Its documents are ordinary tool documents, stored in
`tools/`, and are recorded in a database the same way as any other tool: by
an explicit import of each exact tool version.

The library holds the two composition tools:

| Tool            | Version | Implementation | Purpose                                     |
| --------------- | ------- | -------------- | ------------------------------------------- |
| `run_workflow`  | 1.0.0   | 1.0.3          | Run a child workflow once (ADR 0084).       |
| `loop_workflow` | 1.1.0   | 1.1.3          | Run a child workflow repeatedly (ADR 0090). |

Both run `azathoth workflow invoke` in a child process, so both grant
themselves the variables it needs (ADR 0099), the tracing configuration it
needs to continue a trace (ADR 0100), and the Bedrock configuration and AWS
credentials it needs to run Bedrock models (ADR 0103):

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

`standard_tool_documents()` decodes them in that fixed order:

```python
from azathoth.standard import standard_tool_documents

for document in standard_tool_documents():
    print(document.definition.name, document.definition.version)
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
current revisions:

```text
Installed tool run_workflow@1.0.0 revision 2.
Installed tool loop_workflow@1.1.0 revision 2.
```

A database that already holds implementations 1.0.1 and 1.1.1 gets 1.0.3 and
1.1.3 as revision 3 the same way, and one that holds 1.0.2 and 1.1.2 gets
them as revision 4.

A tool belongs here when it is pure Python, deterministic, works on Windows,
needs no network, and has no side effects outside its inputs. The
composition tools are the one exception: their side effects are Azathoth's
own recorded invocations and runs.
