# ADR 0127: The Remote Serves the Service API

- Status: Accepted; amended by ADR 0133, ADR 0134, ADR 0136, ADR 0137
- Date: 2026-11-17

## Context

A 1.4 remote is a place to push to and pull from. It serves the remote
protocol of ADR 0124, push, pull, content, heads, credentials and the
portfolio, and nothing else. Everything else a team does on its shared
instance, from reading production invocations to promoting a workflow,
happens on the remote's own machine, at its own command line, by whoever
can log in there.

The editor is built to work on any Azathoth instance, and its rule is that
every `azathoth` command has a counterpart there, locally and on a remote.
The command line should reach a remote the same way. Both need a remote
that answers the whole service API, not one built page by page.

A core remote trusts every token-holder as its owner (ADR 0124). The team
tier, built on the remote's seams, needs a name for every thing a caller
might do, so that its roles can be sets of them. Today the remote's
`Action` names only what the protocol does.

This record decides the design 1.6 builds. 1.5 builds the editor's pages
locally, on the service API, and this record is what keeps each of those
pages usable against a remote when 1.6 arrives.

## Decision

### `/v1` mirrors `azathoth.api`

A remote serves every call of `azathoth.api` over HTTP, one route for each,
under `/v1`, beside the protocol routes it already serves. A call's
arguments and its `ApiModel` result are its request and response bodies, as
their own JSON, so the routes add no shapes of their own. Within 1.x the
routes grow only by additions, as the service API does. A call the service
API gains in a later 1.x release gains its route in the same release.

The protocol routes of ADR 0124 stay as they are, and remote protocol 1 is
unchanged, so a 1.4 instance still pushes to and pulls from a 1.6 remote.

A remote says that it serves the service API at `GET /v1/service`, with the
Azathoth version and the service API stability it serves. `Capabilities`
does not change, since clients before 1.6 refuse fields they do not know. A
remote that answers 404 there serves only the protocol, and a client that
needs the service API says so:

```text
The remote <NAME> only serves push, pull and status; upgrade it to Azathoth 1.6 or later to work on it.
```

A refusal from a service route is `{"error": "<MESSAGE>", "code": "<CODE>"}`,
with the status ADR 0124 gives its kind, and `code` the `ApiError` code
the service API already names. A client raises the same `ApiError` the call
raises on a local instance, so code that handles one handles the other. A
caller refused by the policy gets the new `PermissionDeniedError`
(`permission_denied`, 403), whose message is the policy's reason.

### One interface: `Instance`

`api.open(database)` returns an `Azathoth`. The service API gains an
`Instance` protocol, the calls and collections `Azathoth` has, which
`Azathoth` satisfies unchanged, and `api.connect(url, token)`, which returns
a remote `Instance` that makes each call over HTTP. Code written against
`Instance` works on either: the editor, `azathoth-mcp` and the command line.

A remote `Instance` never sends a provider key, and it is given only the
remote's token, read as ADR 0126 reads it: from the variable its name
names. `instance.remotes` on a remote `Instance` lists the remote's own
names; a client's names stay with the client.

### `--remote` on the command line

Every `azathoth` command gains `--remote <NAME>`, which runs it against the
named remote instead of `AZATHOTH_DATABASE`. A command that reads a local
file, such as an import, reads it here and sends its document. A command
that writes a file, such as an export, writes it here.

Five commands never take it, since they run a remote and its workers
rather than call one: `remote serve`, `init`, `worker run`, `worker health`
and `worker needs`. The commands that move work between instances,
`remote push`, `remote pull` and `remote status`, already name their remote,
and `remote add`, `remote list` and `remote remove` keep this instance's
names; none of these takes `--remote` either.

### The action catalog

Every route asks the policy for one named action, and for the resource it
acts on when it names one: a workflow, tool, benchmark, model or run by its
ID. A listing asks for the action once and then for each resource it
returns, and leaves out those the policy refuses, so a policy may decide by
resource. `Action` grows to the full catalog, stable within 1.x:

| Action | What it allows |
| --- | --- |
| `read_capabilities` | Read the remote's capabilities and its service description |
| `push`, `pull`, `read_content` | The protocol of ADR 0124 |
| `read_portfolio` | Read the remote's portfolio |
| `read_catalog` | Browse workflows, tools, benchmarks, goals and their histories |
| `read_runs` | Read runs, invocations, executions and experiments, and their traces |
| `read_restricted` | Read data labelled restricted, wherever it appears |
| `import_workflow`, `import_benchmark` | Import a workflow or benchmark revision |
| `import_goal` | Import a reusable goal (ADR 0133) |
| `import_tool` | Import a tool version, except a process tool |
| `import_process_tool` | Import a process tool |
| `tool_from_mcp` | Make a tool from an MCP server, which starts a command on the server |
| `install_standard_tools` | Install the standard tool library |
| `run_workflow` | Run a workflow or try a step |
| `invoke` | Invoke a workflow in production |
| `promote` | Promote, and roll back, a workflow |
| `authorize_model` | Add a model to the portfolio, and remove one |
| `declare_policy` | Declare what a model's provider does with data |
| `manage_judges` | Add and remove semantic judges |
| `annotate_run` | Give a run feedback and annotations, and resume it |
| `edit_benchmark` | Create a benchmark, add and edit its cases, and turn a run into a case |
| `run_benchmark` | Run a benchmark |
| `optimize` | Optimize a workflow |
| `read_spend` | Read spend and the reports |
| `manage_tokens` | Create and revoke the remote's tokens |

Each call of the service API names its action in its docstring, and the
service API README says it in each call's table, so neither a plugin nor
the editor guesses it. A call that cannot be made without another action's
data asks for both: a run turned into a restricted case asks for
`edit_benchmark` and `read_restricted`.

The core's policy is unchanged: the owner may do everything. No role logic
lives in the core. The team tier's policy maps roles onto these actions,
per person, on each remote.

### High-privilege actions

Five actions let a caller run code on the remote, read what should not
spread, or let others in:

- `import_process_tool`, since a process tool runs a command;
- `tool_from_mcp`, which starts a command on the server to ask it;
- `install_standard_tools`;
- `read_restricted`;
- `manage_tokens`.

The core grants them to the owner, as it grants everything. The team tier
grants no role any of them unless a person is given it by name.

A pushed process tool already runs on the remote whenever a remote job uses
it. `push` therefore carries some of `import_process_tool`'s weight today,
and the team tier's policy asks for both when a push carries a process tool.

### Who may do what

`GET /v1/permissions` returns the actions this caller may take on this
remote, each with the policy's reason when it may not. `POST
/v1/permissions`, given resources, returns the decisions for each. A client
asks before it shows anything that acts, so the editor disables a button and
says why rather than meeting a 403. It is advice, not a guarantee: every
route still asks the policy itself.

A client asks again when it switches to a remote and when it refreshes, and
keeps the answer only for that remote, and only briefly. A local instance
allows everything.

### Long-running work runs on the remote's workers

A run, a benchmark run and an optimization on a remote are jobs, queued as
ADR 0107 queues them and run by the remote's workers. The route that starts
one answers with the job at once, and `GET /v1/jobs/{id}/events` streams its
events as server-sent events, the same `RunEvent`s that `on_event` receives
locally, so the editor's run page watches a remote run as it watches a local
one. Cancelling a job cancels it at its worker.

`GET /v1/service` reports whether any worker has answered recently, so a
client can warn that a job will wait. A remote with no worker accepts jobs,
and they wait.

### A concurrent server

The remote's server answers many requests at once. Each request takes its
own database connection, from a pool on PostgreSQL. On SQLite, reads run
together and writes take turns. This replaces the one-request-at-a-time
server of ADR 0124, so several people can browse, run and watch at once.

### Credentials stay where they are

A remote run uses the remote's provider keys and the credentials its tools
name, checked by name as `/v1/credentials` checks them for a push. A client
never sends a key anywhere; neither the editor nor the command line has a
way to.

### Spend on the remote

The spend and report calls that 1.5 adds are served at `/v1/spend` and
beside it, behind `read_spend`. A remote's spend is only what ran on the
remote itself: its jobs, its workers, and its `azathoth-mcp`. Runs never
travel, so a run on a laptop is that laptop's spend, and a view across
instances adds each one's part, shown apart.

### The audit

Every route tells the audit what it did: the action, the caller, the
resource, and when. `AuditEventKind` grows with the catalog, one kind for
each action that changes something or reads restricted data. The core's
audit still records nothing.

## Consequences

- A remote becomes an Azathoth people work on, not only one they push to.
  The editor, the command line and `azathoth-mcp` all reach it through one
  interface.
- Every 1.5 page that calls the service API through an `Instance` works on
  a remote in 1.6 without being rebuilt. A page that reached around the
  service API would not, so none does.
- The team tier gets a complete, stable catalog to build roles on, and the
  core stays free of roles.
- A 1.4 or 1.5 client keeps pushing to and pulling from a 1.6 remote, but
  works on one only once it is 1.6 or later.
- A core remote is still only as safe as its tokens. With the whole service
  API behind them, a token can now run, promote and authorize, not only
  push. The docs and `remote token create` say so before a token is made.
- Runs on a remote need its workers running, which a remote deployed on
  AWS already has.

## Deferred

- Pulling evidence, `pull --with-data`: executions, experiments and runs.
  Until then, evidence is read through the remote, not copied.
- Redacting restricted output when a run is streamed from a remote.
- A default remote.
- Merging diverged lineages; 1.4 forks, and a person chooses.
- Gating tools, not only models, by sensitivity label.

## Alternatives Considered

### Endpoints for each editor page

Routes shaped for the editor's pages would be quicker for each page, and
would leave the command line and `azathoth-mcp` to want routes of their
own, with three shapes for one call to keep in step. Mirroring the service
API keeps one surface and one client, and remote mode for the command line
comes with it.

### Roles in the core

A role model in the core would decide for every team what its roles are,
and would put the team tier's work in a public repository. The core names
what can be done; a policy decides who may do it.

### Remotes holding each other's tokens

A remote that pushed straight to another, staging to production, would
hold a token for it, and a person's right to ship would become the
remote's. Work moves between remotes through a person's own instance
instead: a pull from one and a push to the other, each checked by that
remote with that person's token for it.

### A new protocol version

Serving the service API as remote protocol 2 would turn away every client
before 1.6, even for the push and pull they already do. New routes, and
a description at `/v1/service`, add the service API without changing what
older clients rely on.

### Running remote work in the request

A run answered inside its request would hold a connection, and a worker's
place, for as long as the run lasts, and would end with the connection.
Jobs already run on workers and survive a dropped client; their events
stream back.
