# Release Validation

This document defines what must be true before a commit on `main` may be
released. [Releasing](../RELEASING.md) gives the steps that check it and
publish the release. This document is the contract those steps enforce.

It answers one question:

> What must be true before this commit ships?

A release must be:

- **internally consistent**: the code, the tests, the examples and the docs
  agree;
- **deterministic**: it passes with no network, no provider and no
  credentials;
- **installable**: the built wheel installs and runs from a clean environment
  on every supported platform;
- **operable**: a new user can follow the guides from a bare machine to a
  promoted, invoked workflow.

## What Release Hardening Finds

Release validation is for finding and fixing:

- broken public journeys;
- stale documentation;
- packaging problems;
- inconsistent command behavior;
- missing lifecycle coverage;
- type or lint regressions;
- accidental nondeterminism;
- contradictions between documented and implemented architecture.

It is not a reason to add unrelated capabilities.

## 1. The Deterministic Gate

The complete repository gate must pass on the commit being released:

```bash
make check
```

That runs `ruff check`, `ruff format --check`, strict `mypy` over
`src/azathoth` and `tests`, and the full `pytest` suite. Windows has no
`make`; [Releasing](../RELEASING.md#deterministic-validation) lists the same
commands for PowerShell.

Continuous integration (`.github/workflows/ci.yml`) runs lint, formatting
and types once. It runs the test suite on Linux, macOS and Windows, with
Python 3.11, 3.12 and 3.13. All nine test jobs must be green.

The deterministic gate must never require:

- network access;
- OpenRouter availability;
- provider credentials;
- paid model execution;
- mutable external service state.

Provider behavior in normal tests comes from controlled implementations or
mocked transports. A green repository then means a green Azathoth, not an
external API that happened to cooperate.

## 2. The Distribution

The release is the built wheel, not the checkout. The release workflow
(`.github/workflows/release.yml`) must:

- build the source distribution and the wheel once;
- require a tag to be exactly `v` plus the version in `pyproject.toml`;
- install the wheel into a clean environment outside the checkout;
- require `azathoth --version` to print `azathoth <version>` and
  `azathoth --help` to succeed;
- publish exactly those files, without rebuilding them.

The packaging tests (`tests/test_package.py` and
`tests/test_distribution_artifact.py`) must also pass. They prove:

- the distribution name, version agreement, Python support, dependencies,
  license, URLs, README and entry point;
- that the wheel ships `py.typed` and the standard tool library;
- that an installed wheel loads the standard tools outside the repository;
- that the wheel installs into a separate environment and runs outside the
  repository;
- that provider-free inspection works from the installed artifact.

The container image is the same release, packaged for deployment (ADR 0101).
The release workflow must:

- publish the image only after the wheel is published, from the same commit;
- require `azathoth --version` inside the image to print `azathoth <version>`
  before anything is pushed;
- push `linux/amd64` and `linux/arm64` as `<version>`, `<major>.<minor>` and
  `latest`.

The container tests (`tests/container`) must pass, in CI's `container` job
and with `make container-test`. They prove:

- the image runs Azathoth under `tini`, as uid 10001, with the venv's
  `python` first on `PATH` and the `otel` and `postgres` extras installed,
  over libpq 15 or later;
- that `init` and the child-workflow example work against a fresh volume;
- that `job run` over standard input prints exactly one result;
- that a read-only root filesystem with a writable `/tmp` is enough;
- that tracing to the console leaves standard output untouched.

## 3. The Documentation

The docs are part of the release. The docs tests (`tests/test_docs.py`) must
pass. They prove:

- every relative link, and every link into this repository on GitHub,
  resolves, including its heading anchor;
- every bash command in a user guide has a PowerShell equivalent, apart from
  sections that name one platform;
- no document shows `workflow optimize` with the removed `--expected` flag.

The tests can't judge accuracy. Before a release, review that each of these
describes the implemented behavior:

```text
README.md
docs/install.md
docs/openrouter.md
docs/getting-started.md
docs/examples.md
docs/concepts.md
docs/release-validation.md
CONTRIBUTING.md
RELEASING.md
examples/**/README.md
src/azathoth/*/README.md
```

Documentation must not describe a planned capability as implemented, or
removed architecture as current. When the code and a document disagree, the
code is right and the document is the bug.

## 4. The Examples

Every checked-in example must:

- decode into Azathoth's workflow, tool or benchmark models, exactly as
  `import` would;
- be covered end to end by the deterministic suite under `tests/examples/`,
  with controlled models where it needs them. The canonical
  `simple-prompt.json` must also match its canonical encoding exactly.

They must also work for a real user, on a real machine, from the built wheel.
Before the TestPyPI trial, run the pre-release examples check in
[Releasing](../RELEASING.md#pre-release-examples-run) on macOS:

- install the locally built wheel into a fresh venv outside the checkout,
  following [Installing Azathoth](install.md);
- run every example in [Examples Tour](examples.md) against a fresh database.

The provider-free examples (word count, child workflow, loop) must print
exactly their documented results. The model-backed examples must complete
with the documented shape of result. A Windows run in PowerShell 7 is
recommended whenever a Windows machine is available.

After the TestPyPI trial, install from TestPyPI into another fresh venv and
repeat the provider-free examples.

## 5. Architecture Invariants

The release must preserve these separations.

### Workflow identity

```text
WorkflowSpecification   durable intent
WorkflowCandidate       executable realization
WorkflowRun             empirical evidence
```

### Models

```text
ProviderModel              current provider truth
ProviderModelObservation   historical observation
ModelCatalog               current normalized metadata
ModelPortfolio             organizational authorization
LanguageModelRegistry      executable implementations
```

Availability, history, authorization, metadata and execution stay separate.

### Production

```text
WorkflowProductionState      current execution authority
WorkflowProductionRevision   immutable audit history
ProductionInvocation         external call identity
WorkflowRun                  execution evidence
```

Production invocation executes current production state. It never infers
authority from the newest revision.

### Optimization

```text
optimization   proposes and evaluates candidates, and reports the winner's models
promotion      changes production
```

Optimization must never deploy, and never change the configured workflow.

### Persistence

Repositories store domain state. They must not become hidden orchestration or
provider-policy layers.

Every repository runs on SQLite and on PostgreSQL (ADR 0102). The PostgreSQL
tests (`tests/persistence`, with `AZATHOTH_TEST_POSTGRES_URL`) must pass, in
CI's `postgres` job and with `make postgres-test`. They prove:

- that every repository stores and reads back the same values on either
  database;
- that revisions, idempotency keys and content stay correct when processes
  race;
- that `init` creates the schema, and that every other command refuses a
  database without it, writing nothing;
- that the CLI's provider-free lifecycle, child workflows and jobs work over
  PostgreSQL;
- that no message shows the database's password.

## 6. Public Boundaries

### The command surface

The installed CLI exposes `init` and these command families: `workflow`,
`run`, `experiment`, `invocation`, `model`, `judge`, `tool`, `goal` and
`benchmark`. [The CLI reference](../src/azathoth/cli/README.md) documents
each.

`--help` and `--version` work without a database, runtime bootstrap or
provider credentials.

### Provider-free use

Initializing a database, importing, listing and showing workflows, tools and
benchmarks, and running workflows built only from tools, need no
`OPENROUTER_API_KEY`:

```bash
azathoth init
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow list
azathoth workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result
printf 'that is not dead which can eternal lie' > words.txt
azathoth workflow run a1000000-0000-4000-8000-000000000001 --input-file words.txt --output result
```

`init` installs `run_workflow@1.0.0` and `loop_workflow@1.1.0` as revision
1, and running it again writes nothing. Both runs print `8`: the second reads
its input from a file (ADR 0096), and its run records the file's URI, media
type, size and digest in a `workflow.input.resolved` event.

### Models

Authorization is durable and survives runtime reconstruction. Deauthorization
removes authorization without pretending the provider model has stopped
existing. A model that isn't currently available can't be newly authorized.
Deauthorization is refused while production depends on the model, or while
it is a judge.

### Configured execution

`workflow run` executes the configured specification through candidate
generation. It never executes production state.

### Optimization

`workflow optimize` searches candidates empirically against a benchmark,
whose cases carry their own expected outcomes, and against latency and cost
targets. It takes no expected value of its own. It must not modify
`WorkflowProductionState` or the configured specification.

### Promotion

`workflow promote` materializes the configured candidate into
`WorkflowProductionState`, with each prompt step on an exact model, and
records a `WorkflowProductionRevision` describing the same behavior.

`workflow promote --experiment` promotes the experiment's top-ranked
candidate instead, rebuilt from the workflow's current revision. Its
signature must match the experiment's exactly. A winner measured on another
revision, or one whose models are no longer authorized, is refused and
nothing is promoted.

### Production invocation

`workflow invoke` executes current production state and persists the
`ProductionInvocation`, its `WorkflowRun` and the association between them.
An undeployed workflow fails explicitly. It never falls back to the
configured workflow.

### Reconstruction

Durable state survives a new process: workflows and their revisions, tools,
benchmarks, the portfolio, judges, provider observations, production state
and revisions, runs, experiments and invocations. A runtime is a
process-local snapshot. Objects built from it don't change when durable state
changes later.

### Secrets

Provider credentials are process-local configuration. They never appear in
durable documents, configuration representations or serialized output.

### Failure semantics

A successful command exits 0 and writes its result to standard output. An
expected command or domain failure exits nonzero and writes its message to
standard error.

## 7. The Acceptance Test

`tests/test_oss_v1_release_lifecycle.py` proves, deterministically, that the
major pieces still work together:

```text
configuration ──► availability ──► authorization ──► configured run
      ──► optimization ──► promotion ──► production invocation ──► durable evidence
```

It must not use the live OpenRouter service, and it doesn't replace the
subsystem tests.

## 8. Optional Live Verification

Live OpenRouter tests are an opt-in layer on top of a green deterministic
gate, never a substitute for one. [Releasing](../RELEASING.md#optional-live-verification)
shows how to enable them. They may consume credits, and they can be affected
by provider downtime, model changes, rate limits and latency.

## Release Candidate Checklist

```text
[ ] make check passes locally
[ ] CI is green: quality, plus tests on 3 platforms x 3 Python versions
[ ] packaging tests pass
[ ] docs tests pass, and the documents above were reviewed
[ ] pyproject.toml and src/azathoth/__init__.py declare the release version
[ ] the pre-release examples run passed on macOS from the locally built wheel
[ ] CI's container job is green, and make container-test passed locally
[ ] CI's postgres job is green, and make postgres-test passed locally
[ ] the TestPyPI trial published, installed and passed the provider-free examples
[ ] no credentials are committed
[ ] live verification, if done, was done after the deterministic gate
```

## What Release Ready Means

```text
the documented journeys work, on macOS and Windows, from the published wheel
the published image runs them too, on amd64 and arm64
the deterministic repository is green on every supported platform
durable boundaries survive reconstruction
production changes only through promotion
optimization stays empirical and reports what it found
provider integration is independently verifiable
```

It does not mean every future convenience exists.
