# Changelog

Each release of Azathoth, newest first. Every change of substance was made by
an [architecture decision](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/README.md), linked from its entry. The
release dates are on the
[GitHub releases](https://github.com/EldritchInc/azathoth/releases) and on
[PyPI](https://pypi.org/project/azathoth-ai/#history).

## Unreleased

Azathoth 1.6 makes a remote an Azathoth people work on, not only one they
push to. So far it names, in code, what a remote asks its policy and tells
its audit for every call of the service API, and what a remote's plugins
may build on; a remote answers its requests together rather than one at a
time, and serves every call of the service API but its jobs, asking and
telling as named; and `api.connect` calls a remote as an instance of its
own. The jobs come later.

### The Action Catalog

- `Action` names all 27 actions of the catalog, the protocol's six keeping
  their values, and `HIGH_PRIVILEGE_ACTIONS` the five that let a caller run
  code on the remote, read what should not spread, or let others in
  ([ADR 0134](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0134-the-action-catalog-in-code.md)).
- `AuditEventKind` gains a kind for each outcome of an action that changes
  something or reads restricted data, so promoting and rolling back are
  told apart; each kind names the action it records
  ([ADR 0134](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0134-the-action-catalog-in-code.md)).
- `azathoth.api.calls` lists every call of the service API once, with the
  actions it always asks, the resource it acts on, what more it asks and
  when, and what it tells the audit; the calls that name an instance's own
  remotes are never served. Every call's docstring, and a new Actions table
  in the service API's README, say the same, and tests hold all three
  together
  ([ADR 0134](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0134-the-action-catalog-in-code.md)).
- `PermissionDeniedError`, `permission_denied`, is what a call will raise
  when a remote's policy refuses it, its message the policy's reason; it is
  never a `NotFoundError`
  ([ADR 0134](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0134-the-action-catalog-in-code.md)).

### A Remote Serves Requests Together

- A remote answers requests together. Every call to its seams and
  repositories runs off the event loop, at most eight at once, so a slow
  policy or a long push holds up no other request, `/health` included
  ([ADR 0135](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0135-a-remote-serves-requests-concurrently.md)).
- A transaction may be read-only, `transaction(read_only=True)`, taking no
  write lock; a write in one raises `ReadOnlyTransactionError`. Everything
  a remote reads, it reads so
  ([ADR 0135](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0135-a-remote-serves-requests-concurrently.md)).
- An SQLite file is put in WAL mode the first time it is opened, so readers
  never wait for a writer; it gains `-wal` and `-shm` files beside it while
  it is open
  ([ADR 0135](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0135-a-remote-serves-requests-concurrently.md)).
- A PostgreSQL database keeps a pool of up to eight connections rather than
  one; a transaction that finds none free for thirty seconds raises
  `DatabaseBusyError`. A transaction begun inside another on the same
  thread raises `NestedTransactionError`, on either database
  ([ADR 0135](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0135-a-remote-serves-requests-concurrently.md)).
- Of two pushes of one lineage built on its latest revision, the second is
  told the lineage diverged, never saved as a fork, between the threads of
  one server and between servers on one PostgreSQL database. A save with
  `fast_forward` raises `NotFastForwardError` when it would not build on the
  latest
  ([ADR 0135](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0135-a-remote-serves-requests-concurrently.md)).
- `azathoth remote serve` refuses to serve an SQLite database another
  server is already serving: SQLite serves one remote process on one
  machine, and PostgreSQL serves more
  ([ADR 0135](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0135-a-remote-serves-requests-concurrently.md)).

### The Service API on a Remote

- A remote serves every call of the service API at `POST /v1/calls/<NAME>`,
  its arguments a JSON object by name and its answer the call's result as
  JSON, read from the call's method so no route is written by hand; bytes
  travel in base64. `azathoth.remote.calling` says how each call travels
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- What a caller changes through a remote is recorded as theirs, under
  their principal's name
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- A call asks the policy its actions about what it names, and each
  condition it names before a change is made or restricted data is sent; a
  listing leaves out what is refused
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- The eight calls that take a callback for their events, such as `runs.run`,
  are answered 501 `job` until a remote runs them on its workers
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- `GET /v1/service` says what a remote serves and its edition, and `GET`
  and `POST /v1/permissions` what the caller may do on it and on each
  resource asked about
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- A service route refuses with `{"error", "code"}`, the code an
  `ApiError`'s own, and the status its kind is given
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- A remote tells its audit before it acts or sends what it read, the push
  route too, and follows a change that fails with `request_failed`, a new
  kind; an audit that cannot be told stops the request, answered 503
  `audit_unavailable`. A push's audit says how many revisions it offered
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- A push carrying a process tool asks `import_process_tool` for it, and is
  told as one, as importing one is
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- `tools.install_standard` installs the standard tool library through the
  service API, and `init`, `tool install-standard` and `api.initialize`
  install it the same way
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- `azathoth remote token create` and `revoke` tell the remote's audit before
  the token changes, as `operator:<AUTHOR>`, and `revoke` now needs an
  author as `create` does
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- A remote reads which providers are on, and their keys, when `remote
  serve` starts
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).

### A Client for the Service API

- `api.connect(url)` returns an instance whose every call is sent to the
  remote, and `instance.remote(name).connect()` connects to a remote an
  instance named, with the token its own variable holds
  ([ADR 0137](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0137-a-client-for-the-service-api.md)).
- `api.Instance` is a Protocol that a local `Azathoth` and a
  `ConnectedInstance` both satisfy, so code written for one runs against
  either; a connected instance's collections are typed as a local
  instance's and take the same arguments
  ([ADR 0137](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0137-a-client-for-the-service-api.md)).
- A refusal through a remote raises the error the local call would have
  raised, with the remote's message: a service route's refusal now names
  the kinds its error descends from, in `kinds`, and a `ModelInUseError`'s
  carries its `dependents`
  ([ADR 0137](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0137-a-client-for-the-service-api.md)).
- `RemoteRefusedError` gains `status` and `refusal`, the status and code
  of a refusal of no kind this Azathoth knows, and `RemoteUnavailableError`,
  `remote_unavailable`, is such a refusal with 503, which may be tried
  again later
  ([ADR 0137](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0137-a-client-for-the-service-api.md)).
- A connected instance refuses the eight jobs before sending anything, as
  a `RemoteRefusedError` with status 501 and refusal `job`
  ([ADR 0137](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0137-a-client-for-the-service-api.md)).

### Plugins

- A remote calls a plugin's seams from several threads at once; Writing a
  Plugin says what that asks of one
  ([ADR 0135](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0135-a-remote-serves-requests-concurrently.md)).
- The remote's README names, under Writing a Plugin, everything a plugin
  may rely on within 1.x, and a test fails if any of it goes missing
  ([ADR 0134](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0134-the-action-catalog-in-code.md)).
- `azathoth.persistence.database_location` finds the database
  `AZATHOTH_DATABASE` names, or `azathoth.db`, as the command line does, so a
  plugin finds the database `azathoth remote serve` does; `run_backfills` is
  exported beside it
  ([ADR 0134](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0134-the-action-catalog-in-code.md)).
- `PersistenceError` is among what a plugin may rely on, so a plugin may
  catch every error the database raises
  ([ADR 0136](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0136-the-service-api-over-http.md)).
- A policy may say more of its edition with an `edition_detail`, such as who
  it is licensed to. Nothing in Azathoth acts on an edition or its detail,
  and a test reads every shipped module to keep it so
  ([ADR 0134](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0134-the-action-catalog-in-code.md)).

## 1.5.0

Azathoth 1.5 brings everything the command line does to the service API.
Production and its rollback; the judge rotation, a person's judgment of a
run, what its steps cited, the runs it started and the runs that never
finished; benchmarks, their cases and their runs; optimization, its
experiments and a winner set beside what it would replace; and the rest of
the catalog, a tool's versions, exports, where a model or a tool is used,
and goals: each is a call of `azathoth.api`, which the command line now
makes with its output unchanged, and which the local editor,
[azathoth-ui](https://github.com/EldritchInc/azathoth-ui), calls to do all
of it. Two things are new everywhere: `azathoth spend` says what an
instance spent, billed and estimated dollars always apart, and `workflow
diff`, `tool diff` and `benchmark diff` say what changed between two
revisions. The database schema does not change, as Upgrading From 1.4
below says.

This release changes what the image runs on AWS only by what it adds: the
stack's one-off `init` task finds its database at schema version 7 and
leaves it there, and its workers run jobs as 1.4's did, each model call's
cost now saying how it is known. Release validation requires a release
that changes what the stack runs to be deployed to an AWS sandbox before it
ships, and no sandbox was available, so this release was not deployed. The
template was read, the worker run against botocore's `Stubber` and the S3
tools against a stand-in for S3, as for every release; what only a real
deployment proves, that the stack's workers run jobs on real SQS and S3, is
unproven for 1.5.0, as what 1.4.0 and 1.3.0 left unproven still is
([Release Validation](https://github.com/EldritchInc/azathoth/blob/main/docs/release-validation.md#9-the-aws-deployment)).

### Production

- `azathoth workflow rollback <WORKFLOW_ID>` returns a workflow's production
  to an earlier production revision, the one before the active revision by
  default, or the one `--to` names. It saves a new revision with the earlier
  one's state, exactly as it ran, and refuses, changing nothing, when there
  is nothing earlier, the revision is already active, or a step has neither
  its fixed model nor an approved substitute still authorized
  ([ADR 0128](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0128-production-through-the-service-api.md)).
- Every production revision records who made it, told as an import's author
  is, and what a rollback restored. `workflow promote`, `workflow
  production` and `workflow revisions` show both; a malformed
  `AZATHOTH_AUTHOR` stops a promotion before anything is written. Revisions
  saved before 1.5 name nobody, and the database schema does not change
  ([ADR 0128](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0128-production-through-the-service-api.md)).
- `azathoth.api` reaches production: `instance.production` reads what a
  workflow's production runs and its revisions, newest first, and promotes
  and rolls back as the command line does. `invocations.list` lists a
  workflow's invocations newest first, and `invocations.resume` continues an
  incomplete one from its journal. Six new errors carry codes of their own:
  `workflow_result_missing`, `experiment_not_found`,
  `candidate_unavailable`, `candidate_rebuild`, `nothing_to_roll_back_to`
  and `model_not_authorized`
  ([ADR 0128](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0128-production-through-the-service-api.md)).

### Judges and a Run's Evidence

- `azathoth.api` keeps the judge rotation: `instance.judges` lists it in
  order, and adds and removes a judge, which must be served now and
  authorized. `judge add`, `judge list` and `judge remove` call it, and
  listing and removing still reach no provider
  ([ADR 0129](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0129-judges-and-a-runs-evidence-through-the-service-api.md)).
- `azathoth.api` takes and reads a person's judgment of a run:
  `runs.record_feedback` records one immutable good or bad judgment, a bad
  one needing a reason and only it taking a corrected output, and
  `runs.feedback` lists a run's judgments newest first. Every `RunSummary`
  and `RunDetail` carries the run's latest judgment as `feedback`, and `run
  feedback` calls the API
  ([ADR 0129](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0129-judges-and-a-runs-evidence-through-the-service-api.md)).
- `runs.annotations` and `invocations.annotations` return the W3C Web
  Annotation collection of every citation a run's steps verified, exactly
  as `run annotations` and `invocation annotations` print it, with its
  annotations
  ([ADR 0129](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0129-judges-and-a-runs-evidence-through-the-service-api.md)).
- `runs.children` lists the runs a run's steps started, oldest first, with
  the step and attempt that started each and how it ended, judged as
  `runs.get` judges it. `run children` renders what it returns, so a child
  whose declared result is missing now shows `failed`, as `run show` does
  ([ADR 0129](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0129-judges-and-a-runs-evidence-through-the-service-api.md)).
- `azathoth run interrupted <WORKFLOW_ID>` lists a workflow's runs that
  started and never finished, newest first, with how often each was
  resumed and the command that resumes it, its invocation's for a run that
  executes one. `runs.interrupted` returns the same list, and `runs.resume`
  continues an interrupted configured run from its journal under its own
  ID, through the same call `run resume` makes
  ([ADR 0129](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0129-judges-and-a-runs-evidence-through-the-service-api.md)).
- Two new errors carry codes of their own: `content_unavailable`, for a
  record of citation checks the content store no longer holds, and
  `run_not_resumable`, for a run that finished, executes an invocation, is
  still held by another process, or whose journal cannot be resumed
  ([ADR 0129](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0129-judges-and-a-runs-evidence-through-the-service-api.md)).

### Benchmarks

- `azathoth benchmark create --name <NAME> --description <TEXT>` creates a
  benchmark with no cases. `azathoth benchmark edit-case <BENCHMARK_ID>
  <CASE_ID>` changes a case's comparison, expected value, description,
  citations or label, keeping its input and where it came from, and
  `azathoth benchmark remove-case` removes one. Each saves the benchmark's
  next revision; a label may be raised but never lowered, and an edit that
  makes a case another's twin is refused
  ([ADR 0130](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0130-benchmarks-through-the-service-api.md)).
- `azathoth.api` reads and changes a benchmark's cases: `benchmarks.cases`
  and `benchmarks.case` read them with where each came from, and
  `benchmarks.create`, `add_case`, `update_case` and `remove_case` change
  them as the command line does. `add_case` turns a run into a case,
  expecting its latest correction when no value is given, or makes one
  from JSON or a file. `benchmark cases`, `case-show` and `add-case` call
  the API, their output unchanged
  ([ADR 0130](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0130-benchmarks-through-the-service-api.md)).
- `azathoth.api` runs benchmarks: `benchmarks.run` and `benchmarks.compare`
  check everything before any case runs, tell each case as it starts and
  finishes, stop between cases when cancelled, keeping the case runs that
  finished and recording no execution, and return what they saved.
  `benchmarks.executions` and `benchmarks.execution` read saved runs and
  comparisons, with the revision each ran, and `benchmark executions` and
  `execution-show` read through them. `benchmark run` and `compare` execute
  through the same calls. A new error, `judge_unavailable`, refuses
  semantic cases no judge may judge
  ([ADR 0130](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0130-benchmarks-through-the-service-api.md)).

### Optimization

- `azathoth experiment compare <EXPERIMENT_ID>` sets an experiment's winner
  beside what promoting it would replace: what production runs now, when
  the experiment holds it, or else the workflow's configured candidate. It
  names each step whose model changes and how each case went on both
  sides, and says what a run cost and took on each, measured from the case
  runs the experiment kept. It says what the winner saves per run, in
  dollars and seconds and as a share of the baseline, a negative saving
  being a cost; projects that over production's invocations of the
  workflow in the last 30 days, labelled as a projection; and ends with the
  command that promotes the winner
  ([ADR 0131](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0131-optimization-through-the-service-api.md)).
- `azathoth.api` reads experiments: `experiments.list` and
  `experiments.get` read a workflow's experiments, every candidate ranked
  with its scorecard, each case's run and evaluation, and the model each
  step ran on. `workflow experiments` and `experiment show` read through
  them, their output unchanged
  ([ADR 0131](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0131-optimization-through-the-service-api.md)).
- `azathoth.api` optimizes: `optimization.optimize` checks everything
  before any candidate runs, tells each generation as it starts and
  finishes and each candidate as it finishes, stops between candidates
  when cancelled, keeping every experiment it finished, and records every
  experiment it names. `workflow optimize` optimizes through the same
  function
  ([ADR 0131](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0131-optimization-through-the-service-api.md)).
- `azathoth.api` compares and checks before promoting:
  `experiments.compare` returns the comparison `experiment compare`
  prints, with its savings and projection, and `experiments.promotable`
  says whether the winner can still be rebuilt from the workflow's latest
  revision with the models authorized now, and why not, saving nothing
  ([ADR 0131](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0131-optimization-through-the-service-api.md)).

### Spend

- `azathoth spend` shows what an instance spent, from `--since` up to
  `--until`, by day, ISO week or month (`--by`) as the clock reads in a
  time zone (`--time-zone`, this computer's by default), so a day the
  clocks change is as long as it was. Each period's spend is grouped by
  workflow, model, provider or source (`--group`), and `--workflow` keeps
  to one. Billed and estimated dollars are said apart, never added, and
  unpriced calls are counted, never taken as free. It covers the last 30
  days through today unless told otherwise, and `--output json` or
  `--output csv` writes the service API's report or a spreadsheet's rows,
  to `--output-file` if named
  ([ADR 0132](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0132-spend-and-reports.md)).
- Every model call's cost says how it is known, as `cost_basis` on its
  reply and its step's metrics: `billed` when its provider reported the
  charge, as OpenRouter does, and `estimated` when Azathoth priced it, as
  Bedrock's are. A judge's call records it too. Costs recorded before 1.5
  read their basis from their provider, and the database schema does not
  change. An OpenRouter reply that names no cost is now unpriced, never
  free
  ([ADR 0132](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0132-spend-and-reports.md)).
- Spend counts each model call once: a step that started child runs is
  counted at its own cost, the children's taken back out, and each child
  run for itself, so a report by model puts every dollar on the model that
  spent it. Production invocations' runs are their own source, and each
  judge's call is judging, on the workflow of the run it judged
  ([ADR 0132](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0132-spend-and-reports.md)).
- `azathoth.api` reports spend: `spend.report` returns a `SpendReport`,
  every period of the range listed, spent in or not, each with its groups
  and totals, as `azathoth spend` prints it, and `api.spend_csv` writes it
  as CSV, RFC 4180, its times with their offsets and its amounts unrounded
  ([ADR 0132](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0132-spend-and-reports.md)).
- On Windows, which keeps no IANA time zone database, Azathoth installs
  `tzdata`, so `azathoth spend` and `spend.report` read any time zone there,
  UTC included; without it, 1.5.0a5 refused every report on Windows
  ([ADR 0132](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0132-spend-and-reports.md)).

### The Catalog

- The design of the rest of the catalog through the service API: a tool's
  versions, exports, where a model or a tool is used, comparing two
  revisions, goals, and making a tool from an MCP server, with
  `import_goal` added to the catalog of actions, and a warning when a
  remote token is made
  ([ADR 0133](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0133-the-catalog-through-the-service-api.md)).
- `azathoth.api` browses the rest of the catalog: `tools.versions` lists a
  tool's versions, and `workflows.export`, `tools.export` and
  `benchmarks.export` return a `DocumentExport`, the text the `export`
  commands print with a file name to suggest, and a benchmark's label.
  `models.usage` and `tools.usage` return where a model or a tool is
  configured, in production and executed, as `model usage` and `tool
  usage` print it. Each of those commands now calls the API, with
  unchanged output
  ([ADR 0133](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0133-the-catalog-through-the-service-api.md)).
- `azathoth workflow diff`, `tool diff` and `benchmark diff` print what
  differs between two revisions, a line per change by its JSON Pointer, or
  that the two are identical; `--output json` writes the service API's
  `RevisionComparison`, which each namespace's `compare_revisions` returns.
  Without `include_restricted`, a restricted case's values are withheld as
  `null`
  ([ADR 0133](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0133-the-catalog-through-the-service-api.md)).
- `azathoth.api` keeps goals: `instance.goals` lists, gets and imports
  them, the new `import_goal` action. Importing a goal already kept,
  unchanged, now keeps nothing and `goal import` says the goal is
  unchanged, where it was refused; another goal with a kept ID is still
  refused
  ([ADR 0133](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0133-the-catalog-through-the-service-api.md)).
- `tools.from_mcp` returns the document of a tool an MCP server serves,
  as `tool from-mcp` prints it, importing nothing; a server that cannot be
  reached or listed is the new `mcp_unavailable` error
  ([ADR 0133](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0133-the-catalog-through-the-service-api.md)).
- `remote token create` warns on standard error, when it makes a token,
  that whoever holds it can do anything the remote's owner can, and from
  1.6 through the whole service API
  ([ADR 0133](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0133-the-catalog-through-the-service-api.md)).

### Toward 1.6

- The design Azathoth 1.6 builds: a remote that serves the whole service
  API over HTTP, `api.connect` and `--remote` to reach it, and a catalog of
  named actions for a remote's policy to decide. Nothing in this release
  implements it yet; the editor's 1.5 pages are built to it
  ([ADR 0127](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0127-the-remote-serves-the-service-api.md)).

### Packaging

- Dependabot proposes new digests of the container image's base, and no
  longer new Python versions, which wait until CI tests them.

### Upgrading From 1.4

Upgrade, and run `azathoth init` as after every upgrade:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

If you serve workflows with `azathoth-mcp`, upgrade it in the same command,
as [Installing Azathoth](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md#upgrading-leaving-and-uninstalling) shows: 1.5 of it requires 1.5 of
`azathoth-ai`.

The database schema does not change: it stays at version 7, and `init`
has nothing of it to migrate. Documents, commands and the service API keep
what 1.4 promised, growing only by additions, and every command that now
goes through the service API prints what it did, but for the few lines
below.

What an existing installation will notice:

- production revisions saved before 1.5 name nobody as their author, and a
  malformed `AZATHOTH_AUTHOR` now stops a promotion before anything is
  written, as it stops an import;
- `run children` shows a child whose declared result is missing as
  `failed`, as `run show` does;
- an OpenRouter reply that names no cost is unpriced, never free, and costs
  recorded before 1.5 read their basis from their provider;
- importing a goal already kept, unchanged, succeeds and says the goal is
  unchanged, where it was refused;
- `remote token create` warns on standard error what a token can do.

On Windows, Azathoth now installs `tzdata`, so spend is read in any time
zone there, UTC included.

## 1.4.0

Azathoth 1.4 is built to be shared. Its public service API, `azathoth.api`,
is what the command line, `azathoth-mcp` and the new local editor,
[azathoth-ui](https://github.com/EldritchInc/azathoth-ui), all call, and it
is stable from this release: within 1.x it grows only by additions. Every
revision records its lineage and who made it. Data can be labelled, and
restricted data reaches only the models declared to neither retain nor
train on it. And a remote lets a team push workflows, tools and benchmarks
from one instance and pull them into another, with their history, and see
where each instance stands against it. Upgrading moves the database schema
from version 2 to version 7, which `azathoth init` does, as Upgrading From
1.3 below says.

This release changes what the image runs on AWS: the stack's one-off
`init` task migrates its database from schema version 2 to version 7, and a
job's input can carry a sensitivity label that decides which models it
reaches. Release validation requires such a release to be deployed to an
AWS sandbox before it ships, and no sandbox was available, so this release
was not deployed. The template was read, the worker run against botocore's
`Stubber` and the S3 tools against a stand-in for S3, and the schema
migrated on SQLite and PostgreSQL, as for every release; what only a real
deployment proves, that the stack's `init` task migrates a real database to
version 7 and its workers run labelled jobs on real SQS and S3, is unproven
for 1.4.0, as what 1.3.0 left unproven still is
([Release Validation](https://github.com/EldritchInc/azathoth/blob/main/docs/release-validation.md#9-the-aws-deployment)).

### The Service API

- **`azathoth.api` is Azathoth's public service API.** The command line,
  `azathoth-mcp` and the local editor all call it. It browses and imports
  workflows, tools and benchmarks, lists the models providers serve, keeps
  the model portfolio, initializes databases, and runs and invokes
  workflows, reporting each step and context change to a callback as it
  happens and stopping when cancelled. It returns its own frozen models,
  each with its equivalent `azathoth` command, and raises errors with
  stable codes. It is stable from this release, under the 1.x promise:
  within 1.x it grows only by additions, and anything removed waits for
  2.0, after a minor release that warns of it
  ([ADR 0120](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0120-public-service-api.md)).
- **`azathoth-mcp` runs each tool call through the service API.** A call
  now asks the providers what they serve, as `azathoth job run` does,
  rather than once while production stays the same, so a model authorized
  or a tool imported reaches a running server at once. A call the client
  cancels cancels its invocation, which the same call under its key resumes
  ([ADR 0120](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0120-public-service-api.md)).
- **The API runs and invokes a workflow on a file.** `RunFile` holds a
  document or an image, JSON or text, checked and kept as `--input-file`
  keeps one, and refused before anything runs when it is not its media type
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).
- **The API checks a workflow document without saving it.** It names every
  problem with where it is and its step; says, step by step, whether a
  document could run here now and on which models; and lists the
  portfolio's models that meet a step's requirements, by the rules a run
  uses
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).
- **The API reads back the runs an instance kept:** a workflow's runs
  newest first, and one run with its input, its result, and each step's
  output, values, measurements and failed attempts
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).
- **The API tries one step of a workflow document alone,** on the inputs
  given, a file among them, reporting its events as a run does and keeping
  no run
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).

### Lineage and Authorship

- **Every revision records its lineage.** Each workflow, tool and benchmark
  revision holds a revision digest that covers its content and every
  revision before it, the revision it was built on, and who imported it.
  Every portfolio entry records its digest, who authorized it and when.
  Upgrading records the lineage a database already holds
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- **Importing a document identical to the latest revision appends
  nothing,** and says so: `Workflow <WORKFLOW_ID> is unchanged at revision
  <NUMBER>.`, and likewise for tools and benchmarks. Before, it appended a
  duplicate revision. Importing an earlier revision's document still
  appends a revert
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- **Who imports is `AZATHOTH_AUTHOR`,** as `Name <email>` or `Name`, or
  else the operating system's username. A malformed `AZATHOTH_AUTHOR` stops
  the import, authorizing a model, and adding a benchmark case. The
  standard tools are recorded as Azathoth's
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- **`workflow show` and `benchmark show` name each revision's digest,
  parent and author,** and history lines end with who imported each
  revision when that is known
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- **The API reports each revision's digest, parent and author,** and each
  portfolio entry's digest, author and time. Imports take `based_on`,
  building on an earlier revision to fork, and return `WorkflowImport`,
  `ToolImport` and `BenchmarkImport`, which say whether a revision was
  created; `api.open` takes the `author` to record
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).

### Sensitivity Labels

- **A run's input, a job's input and a benchmark case may be labelled**
  `public`, `internal` or `restricted`, with `--sensitivity`, an input
  source's `sensitivity` or the service API's `sensitivity=`. Unlabelled
  data is internal and unchanged. A child workflow and a case made from a
  run are never less sensitive than their source, and a benchmark is as
  sensitive as its most sensitive case
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- **Each portfolio model declares what its provider does with data:**
  `model authorize --no-retention --no-training`, or `model policy` at any
  time, which also shows who declared it and when
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- **Restricted input reaches only models declared to neither retain nor
  train on data.** A context prompt step that would send it anywhere else
  sends nothing and says which model and what to declare, and a production
  invocation's caller is told the same. Steps that choose a model, and
  production with approved substitutes, choose a private one first;
  semantic judges and the optimizer's substitutes of restricted cases must
  be private; readiness and model matching take a label
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- **`azathoth-mcp`: an exposure document's tool may take `"sensitivity":
  "restricted"`,** the operator's declaration that its client may hold
  restricted data. Its calls are restricted, and `get_invocation` returns no
  restricted invocation through a tool not so exposed
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- **Labels are shown wherever data is:** the API's run, invocation and
  benchmark views, a `Sensitivity:` line in show commands for data that is
  not internal, a warning on standard error from every command that prints
  restricted data, and the `azathoth.sensitivity` span attribute. Tools are
  not gated by labels in 1.4
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).

### Remotes

- **`azathoth remote serve` serves an instance's workflows, tools and
  benchmarks over HTTP,** for other instances to push to and pull from,
  with the new `remote` extra, which the container image includes.
  `azathoth remote push` and `pull`, and the service API's
  `instance.remote(...)`, send each document's latest revision, the
  revisions it was reached by, and the tool versions, child workflows and
  benchmark content it needs, sending only what the other side lacks.
  Production state, the portfolio and runs never travel
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- **Revision digests are a revision's identity everywhere;** each instance
  numbers what it saves. A remote moves only forward: a push whose lineage
  diverged there is refused, and a pull forks a lineage that diverged here
  on the revision its pulled revisions build on, so nothing is lost
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- **A remote's owner issues bearer tokens** with `azathoth remote token
  create`, shown once and kept only as digests; `list` and `revoke` manage
  them
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- **A remote refuses restricted data unless it is served with
  `--accept-restricted`,** and a pull brings restricted benchmarks only with
  `--include-restricted`
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- **A remote's authentication, policy and audit are seams a plugin
  fills,** through the `azathoth.remote` entry-point group; the core's let
  only the owner in and audit nothing. A remote's capabilities name its
  protocol, versions, edition and plugins, and a client refuses another
  protocol before sending anything
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- **`models.matching(..., scope="catalog")` matches every model the
  providers serve,** marked authorized or not, for a pulled workflow's steps
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- **The API's `remote.status()` compares this instance with a remote:**
  each workflow, tool version and benchmark is in sync, ahead, behind,
  diverged, or held by one side only, a workflow names the revision in
  production at the remote, and each model says whether it is authorized
  here and there. A remote that cannot be reached is no error: its side is
  unknown, and its models are read from the portfolio last read from it,
  which each instance keeps
  ([ADR 0125](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0125-remote-status.md)).
- **A remote answers `/v1/heads`, `/v1/portfolio` and `/v1/credentials`,**
  read-only, under a new `read_portfolio` action and `portfolio_read` audit
  event. The credential check is asked by name, and never returns a value
  ([ADR 0125](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0125-remote-status.md)).
- **`azathoth remote push` warns, after its report,** of a credential its
  tools need that the remote does not set, a child workflow the remote runs
  at another revision or not at all, and a model its steps fix that the
  remote has not authorized; a warning never refuses the push
  ([ADR 0125](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0125-remote-status.md)).
- **`azathoth remote add <NAME> <URL>` names a remote,** with the
  environment variable its token is read from, `AZATHOTH_REMOTE_TOKEN`
  unless `--token-variable` names another; the token itself is never kept.
  `remote list` lists the names and `remote remove` forgets one, with the
  last portfolio read from it. The API's `instance.remotes` does the same
  ([ADR 0126](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0126-named-remotes.md)).
- **`azathoth remote push`, `pull` and `status`, and `instance.remote`,
  take a remote's name or its URL;** anything holding `:`, `/` or `.` is
  read as a URL, so a host given without its scheme is refused as one
  ([ADR 0126](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0126-named-remotes.md)).
- **`azathoth remote status <REMOTE>` reports how each workflow, tool
  version and benchmark relates to the remote's,** which revision is in
  production there, and where each model is authorized; a remote that
  cannot be reached is no failure, its models read from the last portfolio
  kept. `--output json` writes the service API's `RemoteStatus`
  ([ADR 0126](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0126-named-remotes.md)).

### Upgrading From 1.3

Upgrade, and run `azathoth init` as after every upgrade:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

If you serve workflows with `azathoth-mcp`, upgrade it in the same command,
as [Installing Azathoth](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md#upgrading-leaving-and-uninstalling) shows: 1.4 of it requires 1.4 of
`azathoth-ai`.

The database schema moves from version 2 to version 7. An SQLite file is
upgraded the first time it is used. A PostgreSQL database refuses every
command until `azathoth init` has run once, from any one machine, and 1.3
refuses it after that, so upgrade Azathoth on every machine first. `init`
keeps everything the database holds and records the lineage of the
revisions in it; revisions imported before 1.4 name nobody as their author.

Three things an existing installation will notice:

- importing a document identical to the latest revision appends nothing,
  and prints `Workflow <WORKFLOW_ID> is unchanged at revision <NUMBER>.`
  rather than appending a duplicate;
- imports, authorizations and new benchmark cases record
  `AZATHOTH_AUTHOR`, or else your username, and a malformed
  `AZATHOTH_AUTHOR` stops them; history lines end with who imported each
  revision;
- `azathoth-mcp` asks the providers what they serve on every call.

Unlabelled data is internal and runs as it did, so nothing changes until
you label something. Serving a remote needs an extra, installed only by
those who serve one: `azathoth-ai[remote]`.

## 1.3.0

Azathoth 1.3 reads documents and keeps the evidence of where each answer
came from. A workflow can be given a PDF or an image; a prompt step can show
it to a model or cite the passages of it the answer rests on, and every
citation is checked against the text before it is kept. Citations are
scored in benchmarks and optimization, and export as W3C Web Annotations
that link back into the documents, S3 objects among them. A workflow can
declare the schemas of its input and its result, and every production
invocation is held to them; and a step can call a tool another MCP server
serves, pinned to that tool's schemas. Documents, commands, the output of
every command that succeeds, and the database schema are as 1.2 left them.

This release changes what the image runs on AWS: the worker records the
version of every S3 object it reads, and the image now reads PDFs. Release
validation requires such a release to be deployed to an AWS sandbox before
it ships, and no sandbox was available, so this release was not deployed.
The template was read, the worker run against botocore's `Stubber` and the
S3 tools against a stand-in for S3, as for every release; what only a real
deployment proves, that the stack still runs the changed worker and image
on real SQS and S3, is unproven for 1.3.0
([Release Validation](https://github.com/EldritchInc/azathoth/blob/main/docs/release-validation.md#9-the-aws-deployment)).

### Documents In

- **A workflow's input can be a PDF or an image.** `application/pdf`,
  `image/png`, `image/jpeg` and `image/webp` join JSON and `text/*`, by
  reference from the CLI or a worker. The content is checked against its
  media type's signature, kept in the content store, and given to the
  workflow as a content handle naming its digest, media type and size
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).
- **A job's inline input can hold a document as base64, and name its
  origin.** Any inline input may name where its content durably lives, such
  as an S3 object with its version ID and ETag; the origin is recorded with
  the input's digest in the run's `workflow.input.resolved` event. A request
  that names no origin digests exactly as before
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).
- **An `s3://` input records the object version it was read from.** A
  worker records the `VersionId` and `ETag` of the response that held the
  bytes as the input's origin, so evidence names the exact object even after
  the key is overwritten
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).
- **`invocation show` prints an input's provenance.** Its URI or inline
  origin, version, media type, size and digest follow the input under
  `Input Provenance`. A run given a PDF or image cannot become a benchmark
  case yet, and `benchmark add-case --from-run` says so
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).
- **A tool can read a document its run received.** A process
  implementation's `content_inputs` are given as files of the content their
  handles name, written and removed by the engine, so a tool needs no access
  to the content store. A handle naming content the run, or a run above it,
  never received is refused before the tool runs
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md)).
- **A document tool's extraction is checked, kept and recorded by the
  engine.** An implementation's `extraction_output` must be a segmented
  text of content the tool was given. The engine keeps it in the content
  store, records it as a resource of the step, and outputs an extraction
  handle in its place
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md)).
- **The standard `segment_pdf` tool divides a PDF into citable segments.**
  Each text box is a segment, `p<PAGE>.s<N>`, with its page and its box in
  points from the crop box's top-left corner, and every page is listed with
  its size and whether it has text. It refuses a PDF of more than
  `max_pages`, 300 by default, or one that needs a password. It reads PDFs
  with pdfminer.six, which the new `documents` extra installs, and the
  container image includes
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md)).
- **A model step can be shown the documents and images its run received.**
  A template variable bound to a content handle shows the model that content
  where the variable stands, beside the template's text, as a prompt of
  parts. The engine reads the bytes from the content store as the prompt is
  sent, only for content the run, or a run above it, received, and no event
  or run holds them. A prompt of text is unchanged
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **OpenRouter models are shown images and PDFs in OpenRouter's own
  parts.** An image is sent as an `image_url` and a PDF as a `file`, in the
  prompt's order, and a PDF is read by the model itself: the request pins
  OpenRouter's PDF engine to `native`, so no paid OCR service reads it in
  the model's place
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **Bedrock models are shown images and PDFs as Converse blocks.** An image
  is an `image` block and a PDF a `document` block named neutrally, in the
  prompt's order. Converse's limits, 20 images of 3.75 MB and 5 documents of
  4.5 MB, with text beside any document, are checked before anything is
  sent. Bedrock does not say which models read documents, so the pricing
  document may add `file` to a model's input modalities under
  `input_modalities`
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **A model is shown only what its catalog says it reads.** A step that
  shows content declares `image` or `file` among its required input
  modalities, and portfolio selection chooses only models that take them.
  Whatever model a step is bound to, its rendered prompt is checked against
  the model's catalog entry before the model is called
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **An example PDF to try it on.** `examples/documents` holds a two-page
  claim, written by a script byte for byte, a workflow that divides it with
  `segment_pdf` into the segments a model can cite, and one that answers
  from it, citing it. The new
  [Reading Documents and Citing Them](https://github.com/EldritchInc/azathoth/blob/main/docs/documents.md)
  guide walks through both and exports the citations
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md);
  [ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).

### Evidence Out

- **Source anchors say where in exactly which content something is.**
  `azathoth.citations` writes a place in content as W3C Web Annotation
  selectors, under their own names: a quote with its context, a span in
  Unicode code points, and a PDF page or image region. An anchor names the
  content's digest and origin, and the extraction whose text its selectors
  count
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **An extraction is the text a tool took from a source, and its
  segments.** Each segment has an ID a model can cite, its span of the text,
  and, on a PDF, its page and bounding box. The whole output is stored as
  canonical JSON, so its digest names it, and an anchor can be checked again
  from the content store alone
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **A citation is checked against the segment it names, with no model
  involved.** A quote found exactly is `verified`; one found only after
  normalizing whitespace, quotes and dashes is `verified_normalized`; and
  otherwise the check says `quote_not_found` or `unknown_segment`. A found
  quote is anchored by the source's own text, its position, and on a PDF its
  page and box
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **Text can be segmented and cited with no document tool.**
  `segment_text` makes one segment per paragraph, deterministically, under
  a version of its own that changes only when its output does
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **A model step is shown an extraction's segments by the IDs it may
  cite.** A template variable bound to an extraction handle renders its
  segments as `[p1.s2] text` inside a `source` named by the variable. Only
  an extraction a step of the run, or of a run above it, kept is shown
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).
- **A cited step's citations are checked before anything relies on them.**
  A JSON prompt step naming a `citations` policy has every
  `{"source", "segment", "quote"}` in its reply checked against the
  extraction it names and replaced by its check, with an anchor naming the
  source's origin. A citation not verified fails the attempt, so the step
  asks again, unless the policy keeps it, and every check is kept in the
  content store and recorded as the step's `citations` resource
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).
- **A Bedrock model's own citations of a PDF are checked the same way.** A
  text prompt step whose policy is `{"native": true}` has Bedrock cite the
  PDFs it shows; each citation is checked against the segments, on the pages
  it names, of the extraction the step also shows, and the step outputs its
  text with the checks, kept and recorded as any cited step's
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).
- **`invocation show` prints every check a cited step kept.** After the
  result, each cited step of the invocation's run names its record and
  lists its checks, one line each: the status, the source, the segment and
  the quote. A record is read back with `stored_citation_checks`, and each
  check can be verified again from the content store alone
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).

### Evidence in Benchmarks

- **A benchmark case can hold a document.** A case names its input's
  provenance, as a run records it, and a case given a PDF or an image holds
  its handle, with the content kept in the content store by digest.
  `benchmark add-case --from-run` takes a run given a document, and
  `benchmark add-case --input-file` makes a case straight from a file
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **Benchmark, comparison and optimization runs read documents.** Every case
  runs with the database's journal and content, as `workflow run` does, so
  `segment_pdf` reads a case's PDF and a cited step keeps its checks. A case
  whose content the store no longer holds is judged as a failed run
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **A case can require its run to cite the right segments.** An expected
  outcome names the segments its run must cite and whether an unverified
  citation fails it; `benchmark add-case --require-citation claim:p1.s2`
  and `--on-unverified` name them. Each is judged from the checks the run's
  cited steps kept, never from the result, and the case's evaluation
  records how many were met
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **Cited runs are scored on their citations.** A scorecard gains a
  citation score, the fraction of a run's checked citations that verified,
  and a cited run's overall score is the mean of five dimensions, so
  comparisons, experiments and optimization prefer candidates whose
  citations verify. Runs with no cited step score as they always did
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **What a run cited exports as W3C Web Annotations.** `azathoth run
  annotations <RUN_ID>` and `azathoth invocation annotations
  <INVOCATION_ID>` print every verified check as an annotation highlighting
  its anchor's place, in exactly the document version it came from, ready
  for a reviewer's annotation tools; the same checks always export to the
  same bytes
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **A citation links to its page.** `azathoth invocation show --links`
  follows each verified citation with a link to its document at its page:
  the origin for `https` and `file` documents, and a presigned GET of the
  exact object version for `s3://` ones, valid for
  `AZATHOTH_LINK_EXPIRY_SECONDS`, an hour by default
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **Results that cite compare by what they cite.** Before an exact,
  normalized or semantic comparison, every citation and check compares as
  `{source, segment}`, so an expected answer names its citations by segment
  however the model words its quote
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).

### Workflow Contracts

- **A workflow declares the JSON Schemas of its input and its result.**
  `input_schema` describes what the workflow receives, a document as its
  content handle, and `output_schema` its declared result. Both travel into
  production with the promoted workflow, and `workflow show` and `workflow
  production` print them; a workflow without them reads and digests as
  before
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).
- **Every production invocation is checked against its workflow's
  contract.** `workflow invoke`, jobs, workers, MCP calls and child
  workflows share one check against the promoted schemas: an input that
  breaks the input schema fails with `invalid_input` before any run starts,
  and a result that breaks the output schema fails with the new
  `invalid_output`, its run kept. Each names every violation by its JSON
  path, and lists them in its metadata
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).
- **`workflow import` says why a document is refused** when the workflow
  states a reason, such as a schema that is not a JSON Schema
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).
- **MCP tools take their workflow's schemas.** A workflow exposed without
  an operator's `input_schema` takes the promoted workflow's input schema,
  and every workflow tool names an `outputSchema`, the outcome it returns,
  its `result` held to the workflow's output schema
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).

### Calling MCP Tools

- **A tool implementation can bind a tool an MCP server serves.** An `mcp`
  implementation names its server, by the command of a stdio server or the
  URL of an HTTP one, the remote tool, the digest of that tool's schemas
  when it was pinned, and the variable holding an HTTP server's bearer
  token; it runs no source. `tool implementation show` prints the binding,
  and every other implementation reads and digests as before
  ([ADR 0119](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0119-call-mcp-served-tools.md)).
- **A tool step calls the MCP tool it is bound to.** Each call connects
  anew, over stdio or streamable HTTP, and calls the tool only while its
  schemas match the pin; its output is the tool's structured content, or
  its text. A stdio server gets only the variables its implementation
  grants, and an HTTP server the bearer token its authorization variable
  holds, with the step's trace context. Install `azathoth-ai[mcp]` to call
  MCP tools
  ([ADR 0119](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0119-call-mcp-served-tools.md)).
- **`azathoth tool from-mcp` writes an MCP tool's document.** It lists a
  server's tools and prints the named tool's document, its definition
  taking the tool's name, description and schemas and its implementation
  pinned to them, ready for `tool import`; writing it again for a tool
  whose schemas changed shows a new implementation
  ([ADR 0119](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0119-call-mcp-served-tools.md)).
  The new [Calling MCP Tools](https://github.com/EldritchInc/azathoth/blob/main/docs/mcp-tools.md)
  guide walks through one, with an example server in `examples/mcp`.

### Fixes

- **Workflows with tool steps can be compared and optimized.** A tool step
  stated no cost, so a run with one could not be scored; it now states
  that its own work costs nothing, and a step that starts child runs, such
  as `run_workflow`, costs what its children did, read from their journals
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **A command stopped as a process tool starts no longer hangs.** A tool
  cancelled before it was given its inputs is killed, its stdin closed, and
  only then waited for. On a Python without CPython's gh-119710 fix, waiting
  for it with its stdin still open never returned, so a run stopped by
  SIGTERM could keep its lease and never exit.

### Upgrading From 1.2

Nothing changes for an existing installation. Upgrade, and run `azathoth init`
as after every upgrade; it installs `segment_pdf`, the one new standard tool:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

If you serve workflows with `azathoth-mcp`, upgrade it in the same command,
as [Installing Azathoth](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md#upgrading-leaving-and-uninstalling) shows: 1.3 of it requires 1.3 of
`azathoth-ai`.

Reading PDFs and calling MCP tools each need an extra, installed only by
those who use them: `azathoth-ai[documents]` and `azathoth-ai[mcp]`.
`azathoth-mcp` brings the MCP SDK with it.

Three refusals the 1.2 documentation quoted now read differently, for anyone
who matches on their text:

- a tool implementation that is not a process one and declares a command,
  or a timeout, is refused with `Only process tool implementations may
  declare a command.` or `Only process and MCP tool implementations may
  declare a timeout.`, where one message named both;
- the refusal of an unsupported runtime lists `mcp, process, python`;
- `workflow import` adds the reason a document is not a valid workflow, when
  the workflow states one, after `Workflow document is not a valid
  WorkflowSpecification.`

## 1.2.0

Azathoth 1.2 serves workflows to AI clients. `azathoth-mcp`, a new package
released with Azathoth at the same version, offers the promoted workflows an
operator lists as Model Context Protocol tools, to Claude Desktop, IDEs and
agents, locally over stdio or to a team over HTTP behind the organization's
identity provider. Everything 1.1 promised is unchanged: documents, commands,
documented output and the database schema are as they were.

The AWS stack, the worker and the S3 tools are unchanged, and the image only
gained `azathoth-mcp`, which the stack does not run, so this release was not
deployed to the AWS sandbox again
([Release Validation](https://github.com/EldritchInc/azathoth/blob/main/docs/release-validation.md#9-the-aws-deployment)).

### Serving Workflows to AI Clients

- **`azathoth-mcp` serves promoted workflows as MCP tools.** It is a separate
  distribution, released with Azathoth at the same version and requiring its
  minor release. Only the workflows an operator lists in an exposure document
  are offered, each as one tool, under the name and description written for
  it; nothing that changes a workflow is ever offered ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **Every call is a recorded, idempotent invocation** of the workflow's
  active production revision, run as `job run` runs a job request: a repeated
  key replays, an interrupted invocation resumes, and the caller is recorded
  with it. `get_invocation` returns an invocation's input, outcome, caller and
  run, step by step ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **Over HTTP it is an OAuth 2.1 resource server.** It accepts only signed
  tokens from the organization's identity provider, issued for its own URL,
  and grants each tool by its own scope; it advertises them in its Protected
  Resource Metadata, and never logs a token. Without authorization it listens
  only on a loopback address ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **It ships in the container image**, and the release publishes both
  packages together. [Serving Workflows Over MCP](https://github.com/EldritchInc/azathoth/blob/main/docs/mcp.md) covers Claude Desktop, teams and the container
  ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).

### Upgrading From 1.1

Nothing changes for an existing installation. Upgrade, and run `azathoth init`
as after every upgrade:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

To serve workflows over MCP, install `azathoth-mcp` into the same venv. From
then on, upgrade both in one command: each release of it requires its own
minor release of `azathoth-ai`.

## 1.1.0

Azathoth 1.1 runs in production. Programs send it jobs through a queue,
workers on AWS run them against one PostgreSQL database, and a run cut short
by a deploy or a lost machine resumes where it stopped. Workflows compose from
a standard tool library that ships in the package, map a child over a list,
take their inputs by reference, and process data of any size from S3. Models
run on OpenRouter or Amazon Bedrock, and every run can be traced.

### Composing Workflows

- **A standard tool library ships in the package**, installed by
  `azathoth init` ([ADR 0095](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0095-ship-a-standard-tool-library.md)).
  Composing workflows needs no checkout of the repository.
- **Data-shaping tools** pick, build, merge and validate JSON and split, join
  and fill in text: `json_select`, `json_object`, `json_merge`,
  `validate_json`, `chunk_text`, `join_text` and `render_template`.
- **A step input may be a constant**, written in the workflow document
  ([ADR 0094](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0094-constant-step-inputs.md)).
- **Loops are budgeted from their settings**: `loop_workflow` 1.1.0 takes a
  `budget_seconds`, and every process tool is told its own timeout
  ([ADR 0093](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0093-budget-loops-from-their-settings.md)).
- **`map_workflow` runs a child once per item of a list**, several at a
  time, and returns the results in order
  ([ADR 0106](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0106-map-a-child-workflow-over-a-list.md)).
- **A child records where it came from**: the step and run that started it,
  and its root, with nesting bounded by the engine
  ([ADR 0104](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0104-record-lineage-in-a-childs-initial-context.md)).

### Inputs and Jobs

- **An input is a value or a reference**, a `file://` or `s3://` URI with a
  media type, resolved before the run starts and kept by its digest
  ([ADR 0096](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0096-accept-inputs-as-values-or-references.md),
  [ADR 0108](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0108-read-inputs-from-s3.md)).
- **A versioned job envelope** requests an invocation and reports its result,
  with an idempotency key that makes a repeated request replay
  (`azathoth job run`,
  [ADR 0097](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0097-carry-invocations-in-a-versioned-job-envelope.md)).
- **Data larger than an input may be** stays in S3: `split_s3_object` streams
  an object into chunk objects, and `read_s3_object` reads one back
  ([ADR 0110](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0110-split-and-read-s3-objects.md)).

### Running in Production

- **PostgreSQL** keeps durable state for many processes at once, selected by
  a `postgresql://` `AZATHOTH_DATABASE`
  ([ADR 0102](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0102-keep-durable-state-in-postgresql.md)).
- **Interrupted runs resume from their journal**, under a lease one process
  holds at a time (`azathoth run resume`,
  [ADR 0105](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0105-resume-interrupted-runs-from-a-journal.md)).
- **A container image** for amd64 and arm64, with an SBOM and provenance,
  signed by the release workflow
  ([ADR 0101](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0101-ship-azathoth-as-a-container-image.md)).
- **Queue workers** take job requests from SQS, settle each message by its
  result, keep a running job's message hidden, and drain on SIGTERM
  (`azathoth worker run`,
  [ADR 0107](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0107-run-jobs-from-a-queue.md)).
- **One CloudFormation template deploys a fleet** of workers on Fargate, with
  least-privilege IAM, secrets from Secrets Manager and scaling on the queue
  ([ADR 0109](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0109-deploy-on-aws.md)).

### Models and Evidence

- **Amazon Bedrock** runs models beside OpenRouter, with its own discovery,
  IAM policy and prices
  ([ADR 0103](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0103-run-models-on-amazon-bedrock.md)).
- **OpenTelemetry tracing** of every run, step and model call, as an optional
  extra ([ADR 0100](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0100-trace-workflows-with-opentelemetry.md)).
- **A step can report its confidence**, recorded with its outputs
  ([ADR 0098](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0098-record-step-confidence.md)).
- **The optimizer evaluates its final generation**, so a candidate proposed
  last is measured before the winner is chosen
  ([ADR 0091](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0091-evaluate-the-final-generations-proposals.md)),
  and **`workflow promote --experiment` deploys an experiment's winner**
  directly ([ADR 0092](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0092-promote-an-optimization-experiments-winner.md)).

### Security

- **Process tools see only the environment they declare**, beside a small
  base set, so a tool never receives a key it did not ask for
  ([ADR 0099](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0099-give-process-tools-only-the-environment-they-declare.md)).

### Upgrading From 1.0

Upgrade the package, then run `init` once against each database:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

1.1 upgrades a 1.0 database in place the first time it opens it, adding the
tables that record a run as it executes. `init`, which is new in 1.1, then
installs the standard tools, which ship in the package from 1.1 on. A
database holding the composition tools 1.0 shipped as examples gets:

```text
Database: /path/to/azathoth.db (existing)
Installed tool run_workflow@1.0.0 revision 2.
Installed tool loop_workflow@1.1.0 revision 1.
Installed tool map_workflow@1.0.0 revision 1.
Installed tool json_select@1.0.0 revision 1.
Installed tool json_object@1.0.0 revision 1.
Installed tool json_merge@1.0.0 revision 1.
Installed tool validate_json@1.0.0 revision 1.
Installed tool chunk_text@1.0.0 revision 1.
Installed tool join_text@1.0.0 revision 1.
Installed tool render_template@1.0.0 revision 1.
Installed tool split_s3_object@1.0.0 revision 1.
Installed tool read_s3_object@1.0.0 revision 1.
Installed tool segment_pdf@1.0.0 revision 1.
```

Two changes can stop a workflow that ran on 1.0:

- Process tools no longer inherit Azathoth's environment. The standard tools
  grant themselves what they need; a process tool of your own that relied
  on an inherited variable, such as a provider key, must grant it (see
  [Process Environment](https://github.com/EldritchInc/azathoth/blob/main/src/azathoth/tools/README.md#process-environment)).
- A workflow that requires `loop_workflow` 1.0.0, the example 1.0 shipped,
  must name 1.1.0. The 1.0.0 implementation grants itself nothing, so its
  children no longer see `AZATHOTH_DATABASE`, and open `azathoth.db` in
  whatever directory they run in instead of yours. `run_workflow` 1.0.0
  needs no change: `init` gives it its grants as its next revision.

## 1.0.0

The first release: workflows composed from prompt, tool and child-workflow
steps, run and recorded as evidence; benchmarks with exact, normalized,
schema and model-judged cases; an optimizer that searches for cheaper
authorized models; and deliberate promotion to production. Models ran on
OpenRouter, and state was kept in SQLite. Its decisions are ADR 0001 to
ADR 0090.
