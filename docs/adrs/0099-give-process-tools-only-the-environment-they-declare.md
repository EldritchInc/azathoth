# ADR 0099: Give Process Tools Only the Environment They Declare

- Status: Accepted
- Date: 2026-11-01
- Decided in: #116

## Context

A process tool (ADR 0078) runs as a subprocess, and inherits Azathoth's whole
environment (ADR 0084, ADR 0093). That made child workflows easy: the
`run_workflow` and `loop_workflow` standard tools (ADR 0095) run
`azathoth workflow invoke` in a subprocess, and it finds the database and the
provider key exactly where the parent did.

It also gives every process tool every secret Azathoth holds. A tool that
counts words sees `OPENROUTER_API_KEY`, and can write anywhere in the database
named by `AZATHOTH_DATABASE`. Azathoth 1.1 adds more: AWS credentials for
Bedrock and the queue worker, the credential endpoint of a Fargate task, an
OpenTelemetry exporter's authorization header, a Postgres connection string.
Each would reach every tool too.

Tools are imported by operators, but written by anyone: a tool library, a
colleague, a model asked to write one. A tool should see what it needs, and
the operator should be able to tell what that is before running it.

## Decision

A process tool's environment is built from an allow-list, not inherited.

### The base environment

A process tool receives these variables, when Azathoth's own environment has
them, so that ordinary programs start and behave:

| Platform | Variables |
| --- | --- |
| macOS, Linux | `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `LANG`, `LC_*`, `TZ`, `TMPDIR`, `TERM` |
| Windows | `PATH`, `PATHEXT`, `SYSTEMROOT`, `SYSTEMDRIVE`, `WINDIR`, `COMSPEC`, `TEMP`, `TMP`, `USERPROFILE`, `HOMEDRIVE`, `HOMEPATH`, `APPDATA`, `LOCALAPPDATA`, `PROGRAMDATA`, `NUMBER_OF_PROCESSORS`, `PROCESSOR_ARCHITECTURE`, `OS` |

None of them holds a secret. On Windows, where variable names are not case
sensitive, they match in any case.

### Grants

An implementation grants itself further variables by name:

```json
{
  "runtime": "process",
  "command": ["python3"],
  "environment": ["AZATHOTH_DATABASE", "OPENROUTER_API_KEY", "AZATHOTH_WORKFLOW_DEPTH"]
}
```

- An entry is a variable name, `[A-Za-z_][A-Za-z0-9_]*`, or a prefix of one
  followed by `*`, such as `AWS_*`, which grants every variable with that
  prefix.
- A bare `*` is not accepted: no grant means "everything".
- Entries are unique.
- Only process implementations take grants.
- A granted variable that Azathoth's environment does not have stays absent.
  It is not an error; the tool decides what a missing variable means.

A grant is part of the implementation's content, so it is pinned by the
implementation's digest (ADR 0076), and `tool implementation-show` names
it. An implementation without grants
serializes without `environment`, so existing documents keep their digests
(ADR 0077).

Grants belong to the implementation, not to the workflow step that uses it:
the implementation is the code that needs the variable, and a workflow cannot
widen what a tool sees.

### The timeout

`AZATHOTH_TOOL_TIMEOUT_SECONDS` stays managed by the engine (ADR 0093). An
implementation that declares `timeout_seconds` sees it; one that does not
never does, even when Azathoth itself inherited one. It cannot be granted.

### The standard tools

`run_workflow` and `loop_workflow` grant themselves `AZATHOTH_DATABASE`,
`OPENROUTER_API_KEY` and `AZATHOTH_WORKFLOW_DEPTH`, which their child
`azathoth` process needs. Their implementations become versions 1.0.1 and
1.1.1; their IDs and tool versions do not change.

Because their content changes, `azathoth tool install-standard`, and so
`azathoth init`, appends the new implementations as revisions (ADR 0095). A
database that installed the standard tools before this decision runs its
child workflows only after `install-standard` is run again; the release notes
say so.

`AZATHOTH_WORKFLOW_DEPTH` is granted until lineage is recorded in a child's
initial context, which is a separate, planned decision.

### Python tools

A `python` implementation runs trusted, in Azathoth's own process, and sees
whatever Azathoth's process sees. This decision does not change that. A tool
that is not trusted with Azathoth's process belongs in a process
implementation.

## Consequences

### Positive

- A process tool sees no secret it did not ask for, including secrets
  Azathoth 1.1 adds later, without anyone having to remember to strip them.
- What a tool can see is stated in its document, pinned by its digest and
  shown before it runs.
- A run's evidence already names each tool implementation's digest, and so
  exactly what that tool could see.

### Negative

- A process tool that relied on an inherited variable stops seeing it, and
  must grant it. Its document changes, so its digest does too.
- Databases that installed the standard tools before this decision must run
  `install-standard` again before child workflows work.
- A tool that needs an unusual base variable, such as a proxy setting, must
  grant it.
- Python tools are not covered.

## Alternatives Considered

### Strip a denylist of known secrets

Rejected. A denylist has to know every secret's name, including the ones
added next release, the ones an operator's platform sets, and the ones
nobody thought of. The allow-list fails closed.

### Grant variables on the workflow step

Rejected. The tool, not the workflow, is the code that needs a variable, and a
grant on a step would let any workflow widen what a shared tool sees. A grant
on the implementation is reviewed once, with the code.

### Inherit everything unless a tool opts out

Rejected. The safe behavior would be the one nobody asked for.

### Grant everything with `*`

Rejected. A tool that needs many variables can grant a prefix, and a list of
prefixes still says what the tool sees.
