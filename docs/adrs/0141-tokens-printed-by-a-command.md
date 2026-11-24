# ADR 0141: Tokens Printed by a Command

- Status: Accepted
- Date: 2026-11-24

## Context

ADR 0126 named a remote by its URL and the environment variable its token
is read from. That suits a token made with `azathoth remote token create`,
which lasts until it is revoked.

A remote whose owner puts it behind a single sign-on proxy, or whose
policy plugin accepts an identity provider's tokens, is reached with a
token that lasts an hour or so. No variable keeps such a token fresh, and
setting one by hand every hour leaves a long run or an open editor
refused partway through. The remote cannot sign anyone in itself: a plugin
fills the remote's seams and adds no routes (ADR 0134), so there is no
page for a browser to sign in at. Every identity provider ships a command
that prints a fresh token for whoever is signed in to it, such as
`gcloud auth print-identity-token` and
`az account get-access-token --query accessToken -o tsv`.

## Decision

### A name keeps a variable or a command

A name may keep the command that prints its remote's token instead of the
variable that holds it:

```bash
azathoth remote add team https://azathoth.example.com \
  --token-command "gcloud auth print-identity-token"
```

```python
instance.remotes.add(
    "team",
    "https://azathoth.example.com",
    token_command=["gcloud", "auth", "print-identity-token"],
)
```

A name keeps one or the other, never both, and with neither its token is
read from `AZATHOTH_REMOTE_TOKEN`, as before:

```text
Give a remote a token variable or a token command, not both.
```

The command line splits the command as a shell would, and the command is
kept as its arguments: a JSON array, in `remote_token_commands`, which
schema version 9 adds. `NamedRemote.token_command` holds them, and
`token_variable` is `None` for such a name. Naming a remote does not run
its command. `remote list` shows the command, quoted, where a variable
would be:

```text
team  https://azathoth.example.com  `gcloud auth print-identity-token`
```

### Running the command

A command is run as its arguments, never through a shell, so nothing in
it is expanded or interpreted. It is given no input, and has 30 seconds to
print the token on standard output, alone and on one line; whitespace
around it is trimmed. A command that does not is refused as an invalid
argument, before anything is sent to the remote:

```text
Token command `<COMMAND>` exited with status <STATUS>: <SAID>
Token command `<COMMAND>` printed no token.
Token command `<COMMAND>` printed more than a token: it must print the token alone, on one line.
Token command `<COMMAND>` printed no token within 30 seconds.
Token command `<COMMAND>` could not be run: <PROGRAM> was not found.
```

`<SAID>` is what the command said on standard error, on one line, its last
500 characters, which is where a provider's tool says to sign in again.

### Keeping the token

The token a command prints is kept in the memory of the process that ran
it, by the command, and never written down. A JWT is kept until 30 seconds
before the expiry its `exp` claim names, so no request is sent with it
expired; any other token is kept for 5 minutes. A JWT's claims are read
only for when it expires: its signature is the remote's to check. A run
that fails keeps nothing, so the command is run again when next asked.
One caller runs a command at a time, and others asking for its token
meanwhile wait for that run rather than each starting one.

### Where it is used

A named remote is reached with its command's token wherever it is reached
by name: `remote push`, `remote pull` and `remote status`,
`instance.remote(name)`, and every command given `--remote` (ADR 0140). The
command is run when the remote is reached, so one that fails is refused
before anything is sent. A connected instance asks for the token before
each request, so a job followed for longer than one token lasts goes on
with the next.

`api.token_of(remote, environ=None)` returns the token a named remote is
reached with now: the one its variable holds in `environ`, the process's
own environment unless given, or the one its command prints. The editor,
which reaches a remote itself, gets each token from it.

This amends ADR 0126, whose names kept a URL and a token's variable only.

## Consequences

- A remote behind single sign-on, or one whose policy accepts an identity
  provider's tokens, is reached by name with no token set by hand.
- The database schema moves to version 9. An SQLite file gains the table
  the first time it is used; a PostgreSQL database refuses every command
  until `azathoth init` has run once, and 1.6.0b1 refuses it after.
- `NamedRemote.token_variable` may be `None`. Code that read it as text,
  as the editor did, reads `api.token_of` instead.
- A token command runs on this machine as the person running Azathoth,
  with their environment, whenever its remote is reached. Only this
  instance's own database names it, and a remote never serves the names an
  instance gives (ADR 0127).
- A token revoked at the provider before it expires is sent until it is
  replaced: at most until 30 seconds before its expiry, or for 5 minutes.
  Each command-line run is a process of its own, so it starts with none
  kept.

## Alternatives Considered

- **Signing in from the command line, `azathoth remote login`.** A device
  code flow would open the browser and keep a refresh token. It needs the
  remote to say which provider signs its callers in, a route of the core,
  and Azathoth to keep a refresh token on disk. The provider's own tool
  already signs its people in and keeps what it must; a command reaches
  every provider that ships one.
- **Running the command through a shell.** Pipes and variables would
  work, but quoting differs between shells and platforms, and an argument
  would become code. A command that needs a pipe can be a script of its
  own.
- **Running the command for every request.** A provider's tool takes
  about a second to start, and the editor sends a remote many requests for
  one page.
- **Keeping the token on disk between processes.** It would leave a
  bearer token in a file; the providers' tools keep their own, where their
  owners already expect them.
