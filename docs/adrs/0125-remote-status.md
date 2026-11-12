# ADR 0125: Remote Status

- Status: Accepted
- Date: 2026-11-11

## Context

ADR 0124 lets an instance push to and pull from a remote, but says nothing
about where the two stand until something moves. Someone about to ship
asks first: is the remote ahead of me, behind me, or diverged? Is the model
my workflow fixes approved on the team instance? Will a tool I push find
the credentials it needs there? The editor's ship button needs the same
answers, as badges and warnings, before anyone presses it.

A push does not promote and never fails on these: a workflow whose fixed
model the remote has not authorized is received, and fails only when
someone promotes or runs it there, on someone else's instance. That is the
worst place to learn it.

## Decision

### How a lineage relates

A lineage's relation is read from two chains of revision digests, each the
latest revision's ancestry, oldest first: the one held here, and the one
the remote holds.

| Relation | When |
| --- | --- |
| `in_sync` | Both sides' latest revision is the same |
| `ahead` | The remote's latest is one this instance's latest was reached by; a push moves it forward |
| `behind` | This instance's latest is one the remote's was reached by; a pull moves it forward |
| `diverged` | Neither; a push is refused, and a pull forks it here |
| `local_only` | Only this instance holds it |
| `remote_only` | Only the remote holds it |

### What a remote tells a client

Protocol 1 gains three read-only routes. They are additions to a protocol
not yet released, so it stays 1.

| Route | Action | Answers |
| --- | --- | --- |
| `POST /v1/heads` | Pull, decided per lineage | Each lineage asked about, or every one held: its latest revision's chain, number, and, for a workflow, the revision in production |
| `GET /v1/portfolio` | Read portfolio | The models it authorizes, with their declared data policies |
| `POST /v1/credentials` | Push | Which of the variable names asked about its environment does not set |

Reading production state moves nothing, so production still never
travels. The credential check is asked by name, a grant ending in `*` set
when any variable it covers is; no value is ever read back, and the remote
never lists its environment. A portfolio read is audited as
`portfolio_read`, under a new `read_portfolio` action.

### Status

`remote.status(workflows=, tools=, benchmarks=)` reports each component
named, or every one either side holds when none is, with its relation and
each side's latest revision, and each model this portfolio, the remote's,
or a reported workflow's fixed step names, marked authorized here and at
the remote.

Each time it reaches the remote, status keeps the portfolio it read, with
the time, in `remote_portfolio_snapshots`, so schema version 6 adds that
table. A remote that cannot be reached is no error: its side is unknown,
each relation is None rather than a guess, and its models are read from
the snapshot, as of `portfolio_synced_at`. A token the remote refuses, or
another protocol, is an error, so a refusal is never mistaken for being
offline.

### Push warnings

Once a push lands, its report warns, and never refuses, of what would stop
its documents from running at the remote:

```text
Tool <TOOL_ID>@<VERSION> needs <NAME>, which is not set at the remote; its steps fail there until it is.
Step <STEP_ID> of workflow <WORKFLOW_ID> runs workflow <CHILD_ID>, which is in production at the remote as revision <RUNNING>, not <LATEST>, the latest here.
Step <STEP_ID> of workflow <WORKFLOW_ID> runs workflow <CHILD_ID>, which is not in production at the remote; it cannot run there until the child is promoted.
Step <STEP_ID> of workflow <WORKFLOW_ID> uses model <MODEL>, which the remote has not authorized; it cannot run there until the remote's portfolio holds it.
```

A child is invoked, so it runs at its production revision (ADR 0084), and
drift is measured against that. A child named only when its step runs, and
a step that chooses its model by requirements, cannot be checked before
they run, so they are not. A push needing none of these checks asks the
remote nothing more.

## Consequences

- An operator sees where each component stands before pushing or pulling,
  and the editor can badge each one.
- A workflow that would fail at the remote for want of a credential, a
  promoted child or an approved model says so when it is pushed, not when
  someone runs it there.
- Status still answers offline, from the last snapshot, and says how old
  it is.
- A PostgreSQL database must be initialized again for schema version 6.
- A push asks up to three more questions of the remote, only when its
  documents need them.

## Future Work

- `azathoth status` and `azathoth remote add|list|remove` on the command
  line, with remotes named, come with the CLI work that follows.
- Approving a model into the remote's portfolio, and promoting a workflow
  there, from a client: a `manage_portfolio` and a `promote` action, which
  the core's policy grants only the owner, and a team's policy grants
  whoever holds the role for it.

## Alternatives Considered

### Refusing a push that would not run

Refusing a push whose fixed model the remote has not approved would force
approval before sharing, though approving after review of what was pushed
is a legitimate order of work. A warning tells the pusher, and the remote's
promotion still refuses what cannot run.

### Status from the push's own exchange

The have-and-want exchange says which revisions the remote lacks, not
which side is ahead, and nothing of production or the portfolio. Heads
answer all of that in one request, and serve status without a push.

### Listing the remote's environment

Returning the names a remote sets would let any token holder read what
credentials it holds. Asking about named variables answers only what the
pushed tools need.

### Guessing relations offline

Reporting `local_only` for every component when the remote is unreachable
would be wrong for each one the remote holds. An unknown relation says
what is known.
