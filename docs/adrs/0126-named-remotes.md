# ADR 0126: Named Remotes

- Status: Accepted
- Date: 2026-11-12

## Context

ADR 0124 reaches a remote by its URL, with one token, read from
`AZATHOTH_REMOTE_TOKEN`. Every push and pull spells the URL out again, and
an instance that reaches two remotes, a team's and a staging one, must swap
the token's variable between commands. ADR 0125 gave a remote a status
through the service API alone, and left the command line's for this work.

## Decision

### A name for a URL and its token's variable

An instance gives a remote a name, with `azathoth remote add` or
`instance.remotes.add`:

```bash
azathoth remote add origin https://azathoth.example.com
azathoth remote add staging https://staging.example.com --token-variable AZATHOTH_STAGING_TOKEN
```

A name is 1 to 64 letters, digits, `_` and `-`, and stands for a URL and
the environment variable its token is read from, `AZATHOTH_REMOTE_TOKEN`
unless another is named. The token itself is never kept, only where to
find it, as ADR 0119 keeps an MCP server's credentials named and never
written down. A name already given, or one never given, is refused:

```text
Remote <NAME> is already named, for <URL>; remove it first, or choose another name.
No remote is named '<NAME>'; name one with `azathoth remote add <NAME> <URL>`.
```

### Names belong to the instance

Names are kept in the instance's own database, in `remotes`, so schema
version 7 adds that table. Like a git repository's remotes, they are not
shared: two instances may give one remote different names, and nothing
travels to the remote when one is given or removed. `remote list` lists
them by name; `remote remove` forgets one, and with it the last portfolio
read from its URL (ADR 0125), unless another name is kept for that URL.

### A name or a URL

`remote push`, `remote pull`, `remote status` and `instance.remote` each
take a name or a URL. A name holds no `:`, `/` or `.`, so whatever does is
read as a URL, and a bare host is refused as one rather than looked up as a
name:

```text
Remote URL '<VALUE>' is not an http or https URL.
```

A name reaches its remote with the token its variable holds, unless the
service API is given one, and a missing token names that variable:

```text
No remote token was given; set <VARIABLE> to one created on the remote with `azathoth remote token create`.
```

There is no default remote: each command names the one it reaches, which a
name keeps short.

### Status on the command line

`azathoth remote status <REMOTE>` reports what ADR 0125's `remote.status()`
returns, for the documents named with `--workflow`, `--tool` and
`--benchmark`, or for everything either side holds when none is named. It
writes a line per component, with its relation, each side's latest revision
number and the first 12 characters of its digest, and, for a workflow, what
is in production at the remote; then a line per model, with whether it is
authorized here and there:

```text
Status of <REMOTE>: reached.
<LINEAGE>  <RELATION>  here <NUMBER> <DIGEST>  there <NUMBER> <DIGEST>
model <MODEL>  authorized here yes  there unknown
```

A remote that cannot be reached is a status, not a failure, and says how
old the portfolio it reads is:

```text
Status of <REMOTE>: not reached; its side is unknown.
Its portfolio is as last read, at <TIME>.
Its portfolio was never read here.
```

`--output json` writes the `RemoteStatus` instead, with each digest in
full, for scripts and the local editor.

## Consequences

- A team's instances reach their remotes by name, and an instance reaches
  two remotes with two tokens, each in its own variable.
- A PostgreSQL database must be initialized again for schema version 7.
- A remote's name can no longer hold `.`, unlike a token's name, so that a
  host given without its scheme is refused as a URL.
- `remote status` gives the command line, and the local editor through
  `--output json` or the service API, a view of a remote before anything
  is pushed.

## Deferred

- Pulling evidence, `remote pull --with-data`: the runs, invocations,
  experiments and benchmark executions a remote made, which ADR 0124
  deferred, and `remote purge`, which would delete what such pulls brought
  in and nothing an instance made itself. Nothing runs in production at a
  remote yet, so there is no evidence to pull; and the platform team that
  runs a remote can investigate its evidence there, where it already is.
  Its decisions, which evidence, gathered by the documents a pull names,
  copied by ID, withheld when restricted unless asked for, and recorded by
  the remote it came from so purge deletes only that, are for the version
  that adds it, as a new route the remote's capabilities name.
- A default remote, which commands could leave unnamed.

## Alternatives Considered

### Names in a configuration file

A file beside the database would split one instance's state across two
places, and would not follow the instance into a PostgreSQL database
shared by its machines. The database already keeps each remote's last
portfolio.

### Keeping each remote's token

A token kept in the database would be read by anyone who reads the
database, and would sit beside every document it guards. A variable's name
keeps the token where the operator keeps secrets, as ADR 0119 does.

### A top-level `azathoth status`

A command named only `status` would seem to report the instance itself,
its runs or its health. `remote status` sits beside `push` and `pull`, the
commands whose effect it previews.

### Telling names from URLs by their scheme alone

Reading only `http://` and `https://` as URLs would look up a host given
without its scheme as a name, and answer that no remote is named so. Any
`:`, `/` or `.` marks a URL, and the refusal says what was wrong.
