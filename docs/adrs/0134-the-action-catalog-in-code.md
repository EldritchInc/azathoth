# ADR 0134: The Action Catalog in Code

- Status: Accepted; amended by ADR 0136
- Date: 2026-11-21

## Context

ADR 0127 decided that a 1.6 remote serves every call of the service API,
asks its policy for a named action before each, and tells its audit what
each did, and it named the actions; ADR 0133 added one. Until now the
catalog lived only in those records. `Action` named the protocol's six,
`AuditEventKind` its eight, and about thirty of the service API's calls
said in their docstrings which action they are. The rest said nothing, and
nothing checked that what was said was true.

A remote's routes, a policy that maps roles onto actions, and the editor
that disables what a person may not do all need the same answer to one
question for every call: what is asked, and of what. Written in three
places by hand, those answers would drift, and a call that drifted would
be asked the wrong thing, silently.

A policy is a plugin, and a plugin's factory takes no arguments. It finds
the remote's database, keeps its own tables and names whoever runs its
commands with what the core offers, but nothing said which of the core's
names it could count on within 1.x. And a policy names an edition that
nothing must act on, since any plugin may name any edition.

## Decision

### The catalog is the enumeration

`Action` names all 27 actions of ADRs 0127 and 0133, in their order; the
protocol's six keep their values. `HIGH_PRIVILEGE_ACTIONS` names the five
that let a caller run code on the remote, read what should not spread, or
let others in. A refusal says its caller "may not" do an action, so the
three whose value would not read as a phrase are worded: "read the
catalog", "read restricted data", "make a tool from an MCP server". Within
1.x the catalog grows only by additions.

### An audit kind for each outcome

`AuditEventKind` keeps the protocol's eight first, then gains one kind for
each outcome of an action that changes something or reads restricted data.
Kinds are per outcome rather than per action, so promoting and rolling
back, both `promote`, and adding and removing a judge are told apart. Each
kind names the action it records, and a refusal records none. Reading what
is not restricted, the catalog, runs and spend, is not audited.

### Refusal is its own error

`PermissionDeniedError`, `permission_denied`, is what a call raises when a
remote's policy refuses it; its message is the policy's reason. It is never
a `NotFoundError`, so a caller who is refused is not told that what they
asked for is missing.

### One list of every call

`azathoth.api.calls` lists each call of an instance once, as a
`ServiceCall`:

- `actions`: what is asked every time;
- `resource`: the kind of resource and the parameter that names it, such as
  a workflow by its `workflow_id`;
- `lists`: for a listing, the kind it returns, each of which is asked about
  and left out when refused;
- `also`: what is asked only when a condition holds, with the condition in
  words, such as `read_restricted` for a restricted case;
- `audit`: the kinds the call may tell the audit;
- `served`: whether a remote serves it at all.

`read_restricted` is only ever asked when a call would show restricted
data, and every call that may ask it tells the audit `restricted_read`.
Importing a process tool asks `import_process_tool` as well as
`import_tool`. Running a benchmark asks `run_benchmark` alone, so a person
may run a benchmark's cases without being allowed to run its workflow
freely. Only making a tool from an MCP server asks a high-privilege action
every time.

The calls that name an instance's own remotes, `remotes.*` and `remote`,
are never served, since remotes never hold each other's tokens (ADR 0127).
Installing the standard tools has an action and no instance call yet.

A test lists an instance's calls by inspecting `Azathoth`, and fails when
the list leaves one out or names one that is not there.

### Docstrings and the README say the same

Each call's docstring names its actions in one form, "It is the `x`
action", and each condition as ", and for a restricted case the
`read_restricted` action too"; a call never served says so. The service
API's README has one Actions table, a row for each call. Tests read both
and hold them to `azathoth.api.calls`, so neither can drift from what a
remote will ask.

### What a plugin may build on

The remote's README names, under Writing a Plugin, every name a plugin may
rely on within 1.x: the seams, `azathoth.api.calls`, the persistence a
plugin keeps its own tables with, `open_repositories` and
`postgres_database`, the owner's tokens, and `resolve_author`. A test fails
when one of them goes missing or is left out of the README.

Finding the database moves into `azathoth.persistence` as
`database_location`, which the command line calls, so a plugin finds the
database `azathoth remote serve` does by the same rule. A plugin's tables
are its own, and it records their version itself: `Database.initialize`
records the core's schema version, so a plugin that called it could mark a
database the core never initialized as initialized.

### An edition is shown, never acted on

A policy may have an `edition_detail` property: one printable line of at
most 200 characters, such as who its edition is licensed to, read afresh
each time. It is not a member of the `Policy` protocol, so a policy without
it is still one. `Seams.edition_detail` refuses a detail that is not one
short printable line. The capabilities do not change, since clients before
1.6 refuse a field they do not know; the service description will carry it.

Nothing in Azathoth compares or matches an edition or its detail. A test
reads every module Azathoth ships, and fails on one that does. What a caller
may do is the policy's `decide` alone.

## Consequences

- A remote's routes, a policy and the editor can all be built from one
  list, and a call cannot be added without saying what it asks.
- What each call asks is now a promise within 1.x, like the call itself.
  Asking for more later would refuse callers who were allowed before; it is
  done only with a new action or a new condition, and said in the
  changelog.
- A policy can decide by resource, by the condition a call names, and by
  whether an action is of high privilege, without guessing from a route.
- Plugins can be built and upgraded against a promised surface, and the
  core sees at once when a change would break one.
- Nothing a 1.5 remote does changes: the owner may still do everything,
  and the routes that ask the list come in a later change.

## Alternatives Considered

### Actions named per HTTP route

Naming an action for each route of the remote would put the answer where a
request arrives. But the command line and the editor ask the same question
of a call, not of a route, and `api.connect` makes the same calls over
HTTP. One list per call answers all of them.

### One audit kind per action

A kind per action would be shorter. It would leave promoting and rolling
back, or adding and removing a judge, as one event, and an audit that
cannot tell them apart does not say what happened.

### An Action column in each of the README's tables

Most calls are described in prose, and some, such as every call of
`instance.runs`, have no table. A column added to each table would have
missed them; one table of every call cannot.

### The edition's detail in the capabilities

The capabilities are what every client reads first. Clients before 1.6
refuse a field they do not know, so adding one would turn them away from a
remote they push to and pull from today.

### Giving a plugin's factory the remote's database

A factory given its context would not need to find the database itself. It
would also change the seams' entry points from a factory taking no
arguments, which 1.x promises, and break every plugin written to it.
`database_location` gives a plugin the same answer without that.
