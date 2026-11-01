# ADR 0095: Ship a Standard Tool Library

- Status: Accepted; amended by ADR 0099
- Date: 2026-10-31
- Decided in: #112

## Context

Workflows compose through two process tools: `run_workflow` runs a child
workflow once (ADR 0084), and `loop_workflow` runs one repeatedly (ADR 0090).
In 1.0 both lived in `examples/tools/`, which is not part of the wheel. A user
who installed Azathoth from PyPI had no way to compose workflows without
cloning the repository to get the two documents.

Tools reach a database only by deliberate import (`azathoth tool import`),
which records a revision of the exact tool version. That is how every tool's
evidence stays traceable, and it must hold for tools Azathoth ships too. A
wheel cannot run anything when it is installed, so a shipped tool cannot be
imported for the user at install time.

## Decision

Azathoth ships a standard tool library inside the package, in
`azathoth/standard/tools/`. It starts with `run_workflow` and
`loop_workflow`, moved unchanged from the examples.
`azathoth.standard.standard_tool_documents()` returns the library's documents
in a fixed order.

The library is installed by an explicit command:

```bash
azathoth tool install-standard
```

For each standard document, the command compares its content digest with the
latest revision of that exact tool version in the database:

- when the version is not there, the document is imported as its first
  revision;
- when the latest revision has the same digest, nothing is written;
- when it differs, for example because the operator imported a modified
  copy, the standard document is imported as the next revision and becomes
  current. Nothing is edited in place.

Running it again is always safe. `azathoth init` creates the database if it
does not exist and runs the same installation, so a new user starts with:

```bash
azathoth init
```

`init` stops there. Authorizing models needs provider credentials and the
models they make available, so it stays a separate step.

Standard tools are versioned with the package. A new Azathoth release may
ship new versions of them, which `install-standard` adds beside the old ones.
Workflows keep requiring the exact versions they name, so upgrading Azathoth
never changes what an existing workflow runs.

A tool belongs in the standard library when it is pure Python,
deterministic, works on Windows, needs no network, and has no side effects
outside its inputs. The composition tools are the one exception: they run
Azathoth itself, and their side effects are Azathoth's own recorded
invocations and runs.

## Consequences

### Positive

- Composition works from a PyPI install, with no repository checkout.
- One command sets up a new database with everything the examples and
  composed workflows need.
- Standard tools are imported like any other tool, so their revisions and
  evidence are recorded the same way.

### Negative

- A new database has no standard tools until `init` or `install-standard`
  runs. Commands that need them fail as for any unimported tool.
- Each release that changes a standard tool must give it a new version, and
  a new implementation ID for that version.

## Alternatives Considered

### Import the standard tools when the package is installed

Rejected. Wheels have no install-time hooks, and a database is not known at
install time.

### Let the engine resolve packaged tools without importing them

Rejected. A tool that runs without a recorded import has no revision to
trace its evidence to, and would behave differently from every other tool.

### Import the standard tools on first use of any command

Rejected. Writing to the database as a side effect of an unrelated command
is surprising, and an operator could not tell when it happened.
