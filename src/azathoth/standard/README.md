# Standard Tools

`azathoth.standard` is the tool library that ships inside the Azathoth
package (ADR 0095). Its documents are ordinary tool documents, stored in
`tools/`, and are recorded in a database the same way as any other tool: by
an explicit import of each exact tool version.

The library holds the two composition tools:

| Tool            | Version | Implementation | Purpose                                     |
| --------------- | ------- | -------------- | ------------------------------------------- |
| `run_workflow`  | 1.0.0   | 1.0.1          | Run a child workflow once (ADR 0084).       |
| `loop_workflow` | 1.1.0   | 1.1.1          | Run a child workflow repeatedly (ADR 0090). |

Both run `azathoth workflow invoke` in a child process, so both grant
themselves the variables it needs (ADR 0099):

```json
"environment": ["AZATHOTH_DATABASE", "OPENROUTER_API_KEY", "AZATHOTH_WORKFLOW_DEPTH"]
```

No other variable outside the base environment reaches them.

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

There has been one exception. When process tools stopped inheriting
Azathoth's environment (ADR 0099), `run_workflow@1.0.0` and
`loop_workflow@1.1.0` gained their grants as the next revision of the same
versions, implementations 1.0.1 and 1.1.1, because without grants no
existing workflow could run a child at all. A database that installed the
library before that runs `azathoth tool install-standard`, or
`azathoth init`, once to pick them up:

```text
Installed tool run_workflow@1.0.0 revision 2.
Installed tool loop_workflow@1.1.0 revision 2.
```

A tool belongs here when it is pure Python, deterministic, works on Windows,
needs no network, and has no side effects outside its inputs. The
composition tools are the one exception: their side effects are Azathoth's
own recorded invocations and runs.
