# ADR 0133: The Catalog Through the Service API

- Status: Accepted
- Date: 2026-11-20

## Context

The service API (ADR 0120) browses and imports workflows, tools and
benchmarks, and each 1.5 record since has brought one surface of the
command line to it: production (ADR 0128), judges and a run's evidence (ADR
0129), benchmarks (ADR 0130), optimization (ADR 0131) and spend (ADR
0132). What is left of the catalog is still the command line's alone, each
command reading the repositories itself:

- `tool versions` lists a tool's versions;
- `workflow export`, `tool export` and `benchmark export` print a revision
  as the document that imports it again (ADR 0122);
- `model usage` and `tool usage` say where a model or a tool is
  configured, in production and in run history;
- `goal import`, `goal list` and `goal show` keep reusable goals;
- `tool from-mcp` prints the document of one tool an MCP server serves,
  pinned as it is served now (ADR 0119).

The editor drives Azathoth only through the API, so it can do none of
these. Nor can any surface say what changed between two revisions of a
workflow, a tool or a benchmark: a revision's history names its content
digest and whether it repeats an earlier one, but not what differs.

ADR 0127 promised one more thing for 1.5: from 1.6 a remote's token reaches
the whole service API, so it can run, promote and authorize, not only push,
and `remote token create` should say so before a token is made. Its action
catalog also has no action for importing a goal.

## Decision

Every call here is an addition to the 1.x service API. The commands become
thin wrappers over the same calls, and their output is unchanged. Each call
is one of the 0127 catalog's named actions, for a remote's policy in 1.6;
a call that reads another action's data asks for both.

### The catalog's remaining reads

| Call | Returns | Action |
| --- | --- | --- |
| `tools.versions(tool_id)` | Each version of one tool, with its latest revision | `read_catalog` |
| `workflows.export(workflow_id, revision=None)` | A `DocumentExport` | `read_catalog` |
| `tools.export(tool_id, version, revision=None)` | A `DocumentExport` | `read_catalog` |
| `benchmarks.export(benchmark_id, revision=None)` | A `DocumentExport` | `read_catalog`, and `read_restricted` for a restricted benchmark |
| `models.usage(identifier)` | A `ModelUsage` | `read_catalog` and `read_runs` |
| `tools.usage(tool_id)` | A `ToolUsage` | `read_catalog` and `read_runs` |

A `DocumentExport` holds the document exactly as the export command prints
it, so importing it again appends nothing and importing an earlier
revision's reverts to it (ADR 0122), and the file name it suggests, made
from the component's name, a tool's version and the revision:
`word-count.r3.workflow.json`. The editor's download and the command line's
export are the same bytes.

A `ModelUsage` says, for each workflow that depends on one exact model,
whether its configuration names it, each production step and the role it
holds there, and each run that executed it, newest first, as `model usage`
prints it; an unused model has no workflows, and is not an error. A
`ToolUsage` says the same of a tool's identity, with the names its versions
are required by; a tool nothing defines and no run executed is
`not_found`.

### Comparing revisions

| Call | Returns | Action |
| --- | --- | --- |
| `workflows.compare_revisions(workflow_id, before, after)` | A `RevisionComparison` | `read_catalog` |
| `tools.compare_revisions(tool_id, version, before, after)` | A `RevisionComparison` | `read_catalog` |
| `benchmarks.compare_revisions(benchmark_id, before, after)` | A `RevisionComparison` | `read_catalog`, and `read_restricted` for a restricted benchmark |

A comparison is structural: it compares the two revisions' documents, as
their exports are, value by value. A `RevisionComparison` names both
revisions and their digests, says whether they are identical, and lists
each change by its JSON Pointer (RFC 6901), in document order: `added`, with
the value after; `removed`, with the value before; or `changed`, with both.
A list is compared item by item, so a step inserted at the front reads as
each step changing; a document is small enough that this is still read
quickly, and it never guesses at moves. A restricted benchmark's case
values are left out of its comparison, `null` where they would be, unless
the caller may read restricted data, as a case is shown (ADR 0123). An
unknown revision is `not_found`.

`workflow diff <WORKFLOW_ID> <BEFORE> <AFTER>`, `tool diff <TOOL_ID>
<VERSION> <BEFORE> <AFTER>` and `benchmark diff <BENCHMARK_ID> <BEFORE>
<AFTER>` print it, a line for each change:

```text
~ /steps/0/specification/model_selection/model: "acme/large" -> "acme/small"
+ /steps/1: {...}
- /description: "Count words."
```

or that the two are identical. `--output json` prints the API's model.

### Goals

| Call | Returns | Action |
| --- | --- | --- |
| `goals.list()` | Each `GoalSummary` | `read_catalog` |
| `goals.get(goal_id)` | One `GoalDetail`: its description, success criteria and constraints | `read_catalog` |
| `goals.import_document(document)` | A `GoalImport` | `import_goal` |

A goal document that is not valid is `invalid_document`, and an unknown
goal is `not_found`, as `goal show` says. Importing a goal is a new action
of ADR 0127's catalog, `import_goal`, since no listed action allows it;
the catalog grows by addition, and stays stable within 1.x.

### Making a tool from an MCP server

| Call | Returns | Action |
| --- | --- | --- |
| `tools.from_mcp(tool, *, url=None, command=(), authorization=None, grants=(), timeout_seconds=None)` | A `DocumentExport` of the tool's document | `tool_from_mcp` |

It returns the document `tool from-mcp` prints, pinned to the tool as the
server serves it now, and imports nothing: importing it is
`tools.import_document`, `import_tool` or `import_process_tool`, so a
person sees the document before anything is kept. A server named both by a
URL and by a command, or by neither, is `invalid_argument`; one that serves
no tool by that name is `not_found`; one that cannot be reached, or fails,
is a new error, `mcp_unavailable` (502), since it failed the caller, not
the person.

### A token is the owner's

`remote token create` warns on standard error, before it makes a token,
that the token can do whatever its owner can, and from Azathoth 1.6 does so
through the whole service API: run, invoke, promote, authorize models and
read every run, not only push and pull. The remote's guide says the same.

## Consequences

- The editor can list a tool's versions, export any revision, say where a
  model or a tool is used, compare two revisions, keep goals and make a
  tool from an MCP server, through the service API alone.
- What changed between two revisions is said exactly, and a restricted
  benchmark's values are no easier to read in a comparison than anywhere
  else.
- The command line and the API cannot disagree about any of them, since the
  command line calls the API.
- No token is made without its maker being told what it can do.
- With the catalog through the API, 1.5.0b1 is the first beta of 1.5.

## Alternatives Considered

### A text diff of the exports

A line diff of the exported JSON is familiar and needs nothing new. But a
document's formatting is not its content, a moved key reads as a change,
and a text diff cannot leave a restricted value out without leaving the
line out too. A structural comparison says what changed by its path.

### Importing the tool `tools.from_mcp` makes

One call would be shorter. But making the document starts the server's
command, and importing it is a separate decision with its own action, a
process tool's being `import_process_tool`. Keeping them apart lets the
editor show what it would import, and a policy allow one without the other.
