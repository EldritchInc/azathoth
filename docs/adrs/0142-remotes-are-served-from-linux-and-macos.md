# ADR 0142: Remotes Are Served from Linux and macOS

- Status: Accepted
- Date: 2026-11-24

## Context

Azathoth's test suite ran on Linux, macOS and Windows, with every Python it
supports. On Windows it took 23 minutes and more, sometimes passing the
30-minute limit, while the next slowest platform took about 5. Most of that
time went to the tests of serving a remote and running the queue worker:
job runners, their heartbeats and recovery, servers stopped and started
again, worker processes stopped and killed. Starting a process and waking a
thread both cost more on Windows, and twice in one day those tests failed
there on timing alone.

A remote is served, and the worker run, where a team keeps its instance:
from the container image, from the AWS template, or from a Linux server.
What people do on Windows is run Azathoth on their own machine, reach
remotes from it, with push, pull, status, `--remote` and token commands,
and use the editor.

## Decision

### Serving and the worker are tested on Linux and macOS

`azathoth remote serve` and `azathoth worker run` are tested on Linux and
macOS. On Windows each still runs, at its operator's own risk, and says so
once as it starts, the worker once its settings are valid:

```text
Serving a remote on Windows is untested and at your own risk; Azathoth tests serving on Linux and macOS (ADR 0142).
Running the queue worker on Windows is untested and at your own risk; Azathoth tests it on Linux and macOS (ADR 0142).
```

Nothing else about either changes there. A team that serves from a Windows
machine can serve from WSL 2, or from the container image, instead.

### Their tests are skipped on Windows, saying why

`tests/conftest.py` names the modules that test serving a remote or
running the worker, and the few tests of them in modules that test
something else. Their tests are marked `server` on every platform, and
skipped on Windows, each with this reason, so a run lists every test it
left out:

```text
Serving a remote and running the queue worker are tested on Linux and macOS, and on Windows are at their operator's own risk (ADR 0142).
```

Every other test runs on every platform: running workflows and tools
here, the client of a remote, a connected instance, the command line on a
remote, token commands, every documentation test, and `azathoth-mcp`,
which AI clients start on the same machine. A test names the server
modules, and keeps those of reaching a remote, the documentation and the
MCP server off the list; another finds any test elsewhere that serves a
remote or runs the worker and is not on it. Moving a test across the line
is a deliberate change.

## Consequences

- Windows test jobs leave out the slowest tests and the ones that failed
  there on timing; pull requests stop waiting on them.
- A bug in serving or the worker that shows only on Windows is not found
  by CI. That is the risk the warnings name.
- Reaching a remote from Windows, and everything an instance does there on
  its own, stays tested there as before.
- The team tier's server serves through `azathoth remote serve`, so it
  warns on Windows the same way.

## Alternatives Considered

- **Refusing to serve on Windows.** It would make an untested server
  impossible to start by mistake, but would stop anyone who knows the risk
  and wants to try, and WSL 2 is a step away for anyone refused.
- **Running Windows only on pushes to `main`.** Pull requests would stop
  waiting, but every merge would still wait on the slowest platform, and a
  failure there would surface only after the merge.
- **Skipping on Windows by what each test does, a test at a time.** Marking
  whole modules keeps the line in one list that a test holds, rather than
  spread across hundreds of tests.
