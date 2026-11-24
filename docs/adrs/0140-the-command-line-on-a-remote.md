# ADR 0140: The Command Line on a Remote

- Status: Accepted
- Date: 2026-11-23

## Context

ADR 0127 made a remote serve the service API, so that a remote is an
Azathoth people work on, not only one they push to. ADR 0136 served every
call over HTTP, ADR 0137 gave a client that calls a remote as an instance
of its own, and ADR 0138 ran the calls that take minutes as jobs. ADR 0127
also said the command line would work on a remote; until now nothing did:
every command read and wrote the database of the machine it ran on.

Some commands already called the service API over this machine's
database, as ADR 0120 began. Many did not: a run, an invocation, a
benchmark run and an optimization ran in process, and the production,
model and tool commands read repositories themselves. Several printed what
the API did not return: a run's lineage and evaluations, an invocation's
citations, a benchmark's comparison counts, a run's totals, and an
optimization's winners as they were built.

## Decision

### Every command takes `--remote`

Every command takes `--remote <NAME>`, a remote this instance named with
`remote add`, or its URL, and runs on that remote rather than on this
machine's database. Its token is read as a push reads it (ADR 0126).

Fourteen commands never run on a remote, because what they act on is this
machine's or the remote's own: `init`, `worker run`, `worker health`,
`remote serve`, `remote push`, `remote pull`, `remote status`, `remote
add`, `remote list`, `remote remove`, `remote token create`, `remote token
list`, `remote token revoke` and `tool verify`. Each takes the option
hidden, only to say why in a sentence of its own, and exits with status 2,
as a command given an option it does not take does:

```text
tool verify runs a tool's tests on this machine, so it takes no --remote.
```

This amends ADR 0127, which named the remote only by its name and listed
fewer commands that never take the option: the token commands keep the
tokens of the database a remote is served from, and `tool verify` runs a
tool's tests on this machine. ADR 0127's `worker needs` is no command.

### The remote is chosen once, for the whole command

`main` chooses the remote for the command it runs, and every service API
instance the command asks for is then the one connected to it, made once
and closed when the command ends. It connects before the command does
anything, so a remote with no such name, or whose token is not set, is
refused in one line, with status 1, by every command alike.

A command that asks for this machine's repositories while a remote is
chosen is refused, so it never reads here what it was asked to read
there:

```text
This command reads this machine's database itself, which --remote does not reach.
```

A refusal of the service API that a command does not report itself, such
as a remote that cannot be reached or a caller its policy refuses, is
reported in one line with status 1. That holds without `--remote` too, so
an API error no command catches is no longer a traceback.

### Here runs as it ran; there prints as here

A command run without `--remote` keeps the path it had: a run, an
invocation, a benchmark run or comparison and an optimization still run in
process here, as do the production and model commands. Given `--remote`,
each makes its call of the remote's service API and prints exactly what it
prints here: the same lines on standard output and standard error, the
same records in JSON Lines, and the same exit status. Tests run each
command twice over one database, here and on a remote serving it, and
compare the two.

Commands that only read durable state, such as `benchmark show`, `tool
show`, `workflow show` and `run show`, read through the service API here
too, so one way of reading serves both.

### Runs on a remote are followed as they run here

`workflow run`, `workflow invoke`, `job run`, `run resume`, `invocation
resume`, `benchmark run`, `benchmark compare` and `workflow optimize` run
as jobs on the remote (ADR 0138). A run's step messages and records are
shown as its events arrive. The call runs on a thread of its own while the
command waits for it, so Ctrl-C or SIGTERM cancels the job at the remote
and waits up to 30 seconds for it to stop before the command stops as it
would here.

A file given as input is read and checked here, under the command line's
input policy, which reads only `file:` references, and sent as a file: a
reference to S3 is refused alike here and on a remote. The instance that
runs the call keeps the file's content in its own content store.
`invocation show --links` makes its links with this machine's credentials.

A command a step of another run started runs where its parent runs, so it
takes no `--remote`:

```text
A run another run's step started runs where its parent runs, so it takes no --remote.
```

What a remote records, an import, an authorization or a declared policy,
is recorded as the caller its token names (ADR 0136).

### The service API returns what the commands print

So that every command can print from the service API what it printed from
the database, the API's views gain:

- `RunSummary.source`, what made a run; `RunDetail.lineage`, where a child
  run sits, and `RunDetail.evaluations`, its judgments with their evidence;
  `RunStepDetail.resources`, what a step's strategy used; and
  `StepFinished.emits_values`, whether a step's values follow it.
- `InvocationSummary.error_code`; `ProductionState.emissions`, each value
  production returns and where it is read; and on `InvocationDetail`, its
  `request_digest`, `lineage`, `input_provenance` and `citations`.
- `BenchmarkDetail.cited_cases` and `comparisons`; and each workflow of a
  benchmark execution, its `total_tokens`, `total_latency_ms` and
  `total_cost_usd`, summed from its case runs while every one is kept.
- `OptimizationSummary.workflow_name`, `initial_candidates` and
  `final_experiment`, and each generation's `experiment`: what it judged,
  what judging cost, and its winner's steps and scorecard.
- Five calls, each the `read_catalog` action: `tools.definition`,
  `tools.implementations`, `tools.implementation`, `tools.test_cases` and
  `tools.test_case`. They read a tool's current definition,
  implementations and test cases, as the tool commands always have.

### A call's argument that is a model or JSON is read as the model first

`runs.invoke` takes its input as a JSON value or a file. Read over HTTP,
a file would be taken for the JSON object it is written as. An argument
whose type is a union of models and a JSON value is read as each model
first, and as the value only after, so a file arrives as a file.

## Consequences

- Every command but fourteen works on a remote exactly as it does here,
  and a test requires each to have a test that says so.
- A command whose call is refused by a remote's policy says why in the
  policy's words, in one line.
- Some refusals here now use the service API's words: `benchmark run` and
  `benchmark compare` refuse a benchmark with no cases before any case
  runs, rather than ending in a traceback or naming no case recorded, and
  `benchmark compare` and `workflow optimize` refuse fewer than two
  workflows, targets not above zero and no generations as the API does.
- `tool install-standard` given `--remote` prints each tool once the
  remote answers, so one that stops the installation is reported without
  the tools installed before it.
- A run here and a run on a remote are two paths kept alike by tests. A
  later decision may run everything here through the service API too, once
  nothing is lost by it.

## Alternatives Considered

### Every command through the service API, here too

Running every command here through the service API would leave one path,
but a run, a benchmark and an optimization here would then be reported
from what the API returns once they end, not as they go, and the
production and model commands would change what they print. Keeping the
path here, and proving the remote's alike, changes nothing for anyone who
never names a remote.

### A remote that runs the command line

A remote could run the command it is sent and return what it printed.
That runs whatever the remote's command line is, as whoever the server
runs as, and the policy could no longer ask, per call, what the caller
may do. Calling the service API keeps every call asked and told.

### Refusing only the commands not yet moved

Commands could have refused `--remote` until each moved. They did, while
the work went on; every one has moved, so only the fourteen that never
run on a remote refuse it.
