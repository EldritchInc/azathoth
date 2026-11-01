# Contributing to Azathoth

Azathoth is developed around strict architectural boundaries, deterministic
evidence, and test-driven changes.

Contributions should preserve those properties.

This guide describes the development expectations for the Azathoth codebase.

## Development Environment

Clone the repository, create a virtual environment in it, and install the
project in editable mode with its development dependencies.

macOS and Linux:

```bash
git clone https://github.com/EldritchInc/azathoth.git
cd azathoth
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Windows (PowerShell 7):

```powershell
git clone https://github.com/EldritchInc/azathoth.git
Set-Location azathoth
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

[Installing Azathoth](docs/install.md) covers getting a suitable Python, the
PowerShell execution policy, and UTF-8 output on Windows. Keep the venv
active while you work: the process tools in the examples and tests start
`python` from the `PATH`, and it must be the environment Azathoth is
installed in.

Confirm the installed CLI:

```bash
azathoth --version
```

Run the complete quality gate:

```bash
make check
```

Windows has no `make`; [Releasing](RELEASING.md#deterministic-validation)
lists the same commands for PowerShell.

## Development Philosophy

Azathoth favors explicit domain boundaries over convenience abstractions that
hide authority or mutable state.

Changes should preserve distinctions such as:

```text
durable intent
    ≠
runtime implementation

provider availability
    ≠
organizational authorization

strategy behavior
    ≠
execution evidence

execution
    ≠
evaluation

evaluation
    ≠
scoring

scoring
    ≠
optimization

optimization
    ≠
promotion

production state
    ≠
production revision
```

A contribution that makes one of these boundaries less explicit should be
treated as an architectural change, not a local implementation detail.

Azathoth also keeps one product boundary: workflows are composed, and code
belongs in tools. A behavior that can be expressed by composing existing
steps, tools and child workflows belongs in a workflow document, not in a new
engine feature. New code should usually be a tool, or should make tools and
composition more capable. See [Concepts](docs/concepts.md#composition-not-code).

## Test-Driven Development

Behavior changes should begin with a test that demonstrates the required
contract.

The normal sequence is:

```text
write failing test
      │
      ▼
implement smallest behavior
      │
      ▼
make focused test green
      │
      ▼
run broader subsystem tests
      │
      ▼
run complete repository gate
```

Tests should prove behavior at the lowest useful public boundary.

For example:

```text
domain invariant
    domain-model test

repository contract
    repository test

runtime composition
    runtime test

CLI behavior
    CLI/application test

installed application lifecycle
    console-script lifecycle test
```

Do not use an end-to-end test as a substitute for missing domain tests.

Likewise, do not rely exclusively on isolated unit tests when a feature exposes
a public lifecycle that should be proven across composition boundaries.

## Deterministic Tests by Default

The normal Azathoth test suite must remain deterministic and independent from
external provider availability.

Provider-backed behavior should normally be exercised with controlled
implementations or mocked HTTP transports.

For example:

```text
OpenRouter adapter
      │
      ▼
httpx.MockTransport
      │
      ▼
deterministic provider response
```

Normal development and continuous integration must not require:

```text
external provider availability

real API credentials

paid API usage

current provider response behavior
```

This keeps the normal repository gate reproducible.

## Live Provider Tests

Azathoth also contains explicit opt-in OpenRouter verification.

Live tests are disabled by default.

Enable them only when intentionally testing real provider behavior:

```bash
export AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1
export OPENROUTER_API_KEY='YOUR_OPENROUTER_API_KEY'
```

Individual live tests may additionally require:

```text
OPENROUTER_TEST_MODEL
```

or:

```text
OPENROUTER_TEST_MODELS
```

depending on the test.

For example, a single-model live test may be configured with:

```bash
export OPENROUTER_TEST_MODEL='<provider-native-model-id>'
```

Multi-model verification uses a comma-separated list:

```bash
export OPENROUTER_TEST_MODELS='<model-a>,<model-b>'
```

Live tests may consume provider credits.

They may also fail because of external service behavior unrelated to a code
regression.

They are therefore verification tools, not part of the deterministic quality
gate.

## Container Tests

The container image (ADR 0101) is tested in two ways.

`tests/container/test_dockerfile.py` and `tests/container/test_workflows.py`
read the `Dockerfile` and the GitHub workflows, need no Docker, and run with
every other test.

`tests/container/test_image.py` builds the image and runs it: its version
and user, `init`, the child-workflow example, a job over standard input, a
read-only root, and tracing. It needs a running Docker engine, so it is
disabled by default. With Docker running:

```bash
make container-test
```

This builds the checkout as `azathoth:test`, then runs the image tests
against it. To test an image built some other way, name it:

```bash
AZATHOTH_RUN_CONTAINER_TESTS=1 AZATHOTH_CONTAINER_IMAGE=<IMAGE> python -m pytest tests/container -ra
```

CI's `container` job runs them on every pull request. Run them locally
whenever a change touches the `Dockerfile`, `.dockerignore`, the standard
tools, process tools, or how Azathoth finds its database.

## PostgreSQL Tests

Every repository runs on SQLite and on PostgreSQL (ADR 0102), and
`tests/persistence` runs each of their tests against both. Without a server,
the PostgreSQL half is skipped. With Docker running:

```bash
make postgres-test
```

This starts a throwaway `postgres:17` container on `127.0.0.1:54329`, runs
`tests/persistence` against it, and stops it. To use a server of your own,
name a database the tests may create schemas in:

```bash
AZATHOTH_TEST_POSTGRES_URL=postgresql://<USER>:<PASSWORD>@<HOST>/<DATABASE> python -m pytest tests/persistence -ra
```

Each test gets a fresh schema of its own, which it drops when it ends, so
tests never see one another's rows, and the database is left as it was.

CI's `postgres` job runs them on every pull request. Run them locally
whenever a change touches SQL, a repository, a `Table`, or
`azathoth.persistence`. A repository's SQL must be the subset both
databases share (see [`azathoth.persistence`](src/azathoth/persistence/README.md#writing-sql-once)).

## Code Quality

While working, let ruff fix and format what it can:

```bash
python -m ruff check --fix .
python -m ruff format .
```

Before considering a change complete, run the complete gate:

```bash
make check
```

which runs:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src/azathoth tests
python -m pytest
```

`mypy` runs in strict mode, configured in `pyproject.toml`, over both the
package and the tests.

The repository expects:

- formatted code;
- clean linting;
- strict static typing;
- deterministic automated tests; and
- the complete project quality gate to pass.

## Type Safety

Azathoth uses strict typing as part of its architecture.

Prefer:

```text
explicit protocols

immutable typed models

narrow function contracts

domain-specific values
```

over:

```text
untyped dictionaries

implicit duck typing with undocumented assumptions

shared mutable application state

broad catch-all service objects
```

When a structural protocol exists, implementations should satisfy the protocol
without unnecessary inheritance.

## Immutability

Core domain artifacts are generally immutable.

Do not introduce in-place mutation merely for convenience.

Prefer:

```text
old value
    │
    ▼
explicit operation
    │
    ▼
new value
```

or an explicit repository replacement operation where the domain intentionally
models current mutable-by-replacement state.

Historical evidence should not be mutated after it has been recorded.

## Persistence

Repositories persist domain artifacts.

They should not silently own:

- orchestration;
- network calls;
- provider selection;
- evaluation;
- optimizer policy; or
- production authority beyond the domain artifact they explicitly store.

Persistence code should remain boring.

A repository is written once, as a `Sql…` class against `Database`, and runs
on SQLite and PostgreSQL alike. Its tests use the `database` fixture of
`tests/persistence`, so they run on both.

That is a feature.

## Ordering

When order has semantic meaning, preserve it explicitly.

Examples include:

- context events;
- workflow steps and dependency resolution;
- repository insertion order;
- benchmark cases;
- candidate populations;
- model portfolios; and
- production model substitutions.

Do not reconstruct semantic ordering from timestamps when the domain already
has an explicit sequence.

## Errors

Expected domain failures should use explicit domain or application boundaries.

Do not convert meaningful failures into:

```text
None

false

empty collection
```

unless that absence is the documented contract.

Likewise, avoid broad exception swallowing.

If a lower-level failure is wrapped, preserve the original exception as its
cause when useful for diagnosis.

## CLI Changes

The CLI is an application composition layer over the same Azathoth domains.

A CLI contribution should not create a second implementation of domain
behavior.

Prefer:

```text
argparse
    │
    ▼
thin CLI application service
    │
    ▼
existing domain operation
    │
    ▼
renderer
```

instead of:

```text
argparse handler
    │
    ▼
new hidden domain semantics
```

Successful operator output belongs on standard output.

Expected command failures belong on standard error and should return a nonzero
process status.

## Public Documents

The JSON files accepted by:

```bash
azathoth workflow import <FILE>
azathoth tool import <FILE>
azathoth benchmark import <FILE>
```

are the canonical serialized forms of Azathoth's own models:
`WorkflowSpecification`, tool documents and benchmark datasets. They are not
a separate tutorial format or CLI schema. Importing never overwrites: each
import appends a revision.

When serialization changes, the checked-in examples and their tests must
change with it, in the same commit.

## Examples

Each example lives in its own folder under `examples/`, laid out the same
way:

```text
examples/<name>/
├── README.md        what it shows, its document IDs, and how to run it
├── workflows/       workflow documents
├── tools/           tool documents, where it needs its own
└── benchmarks/      benchmark documents
```

Smaller shared documents live in `examples/workflows/`, `examples/tools/`
and `examples/benchmarks/`.

Every example must:

- be covered by tests under `tests/examples/` that decode its documents and
  run it end to end with controlled models, so the deterministic suite
  proves it works without a provider;
- show its commands in its README;
- appear in [Examples Tour](docs/examples.md), in the order of the ideas it
  builds on, with bash and PowerShell commands and its expected result.

Prefer examples whose deterministic work is done by tools, and whose
workflows are composition. That is the pattern users copy.

## Architecture Decision Records

Significant architectural decisions are recorded under:

```text
docs/adrs/
```

An ADR is appropriate when a change alters a durable architectural rule such
as:

- subsystem ownership;
- public domain boundaries;
- production authority;
- persistence semantics;
- provider abstraction;
- model-selection authority;
- evaluation or optimization responsibilities;
- public workflow representation;
- runtime composition;
- durable identity; or
- a cross-cutting operational contract.

A small implementation detail does not require an ADR merely because code
changed.

Ask:

> Will a future contributor need to know why this boundary exists in order to
> avoid accidentally undoing it?

If yes, an ADR is probably appropriate.

Records live in `docs/adrs/`, one file per decision, named
`NNNN-short-title.md`. `tests/test_adr_records.py` enforces their form:

- records are numbered from `0001` with no gaps;
- each file starts with `# ADR NNNN: <Title>`, carrying its own number;
- the next two lines after the blank line are the status and the date:

  ```text
  - Status: Accepted
  - Date: <YYYY-MM-DD>
  ```

  The status is `Accepted`, `Proposed` or `Deprecated`. A record whose
  decision was later changed keeps its text and adds
  `; amended by ADR NNNN` to its status;
- `docs/adrs/README.md` lists every record, in order, with its exact title.

A record written after the pull request that made the decision adds a
`- Decided in: #<PR>` line after the date.

Records are never rewritten to match later decisions. A changed decision gets
a new record, and the old one is marked as amended.

## Documentation

Documentation describes implemented behavior. Don't describe planned
architecture as though it already exists. When the code and a document
disagree, fix the document.

The documentation set is:

```text
README.md                    the front door, also the PyPI description
docs/install.md              installing on macOS and Windows
docs/openrouter.md           a key, models and judges
docs/getting-started.md      one workflow from import to production
docs/examples.md             the examples tour
docs/concepts.md             architecture and design
docs/release-validation.md   what a release must prove
docs/adrs/                   architecture decisions
RELEASING.md                 how a release is made
CONTRIBUTING.md              this guide
examples/**/README.md        each example
src/azathoth/<subsystem>/README.md   each subsystem
```

When a feature changes a public subsystem boundary, update that subsystem's
README. When it changes something users do, update the guides that show it.

`tests/test_docs.py` enforces the mechanical rules:

- relative links, and their heading anchors, must resolve;
- links in `README.md` are absolute GitHub links, because PyPI renders the
  README without the repository, and they must resolve too;
- in the user guides (install, OpenRouter, getting started, examples), every
  bash block is followed by its PowerShell 7 equivalent. A section whose
  heading names one platform, such as `### macOS` or `### Windows: …`, may
  hold commands for that platform only;
- no document shows a `workflow optimize` command passing the removed
  `--expected` flag.

A new user guide is added to `USER_GUIDES` in that test.

The implementation and tests remain authoritative.

## Commit Scope

Prefer small commits with one architectural purpose.

Examples:

```text
test(workflows): prove explicit production fallback behavior

feat(workflows): resolve explicit production substitutes

docs(workflows): document production model resolution
```

Avoid mixing unrelated refactors, documentation cleanup, feature work, and
behavior changes into one commit.

Small commits make architectural review and regression isolation easier.

## Before Opening a Pull Request

Run:

```bash
python -m ruff check --fix .
python -m ruff format .
make check
```

Then review the diff for:

```text
accidental public API changes

stale documentation

unnecessary mutable state

new hidden authority

provider-specific leakage into neutral domains

persistence performing orchestration

tests that depend on external services

changes that deserve an ADR
```

## Pull Request Expectations

A useful pull request explains:

- what behavior or documentation changes;
- why the change belongs at that architectural boundary;
- what remains intentionally out of scope;
- which tests prove the behavior; and
- whether any public contract changed.

For architectural work, describe the before/after responsibility boundary.

Distinguish clearly between:

```text
new behavior

and

making existing behavior safer, clearer, or more verifiable
```

## Definition of Green

A normal contribution is green when:

```text
formatting
    passes

linting
    passes

strict typing
    passes

deterministic tests
    pass

complete repository check
    passes
```

Live OpenRouter tests are intentionally outside this default definition.

A failure in an explicitly requested live verification should still be
investigated, but it is not equivalent to a deterministic repository regression.

## Releasing

Release-level verification has stricter expectations than an individual
change. [Release Validation](docs/release-validation.md) defines what a
release must prove, and [Releasing](RELEASING.md) gives the steps, including
the pre-release examples run on macOS.

## Central Rule

When in doubt:

```text
make the domain explicit

record evidence

keep authority narrow

test the boundary

document what actually exists
```