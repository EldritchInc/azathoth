# Contributing to Azathoth

Azathoth is developed around strict architectural boundaries, deterministic
evidence, and test-driven changes.

Contributions should preserve those properties.

This guide describes the development expectations for the OSS V1 codebase.

## Development Environment

Create a virtual environment from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Confirm the installed CLI:

```bash
azathoth --version
```

Run the complete quality gate:

```bash
make check
```

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

## Code Quality

Before committing a change, run:

```bash
ruff format src tests
ruff check src tests
mypy src
pytest
```

Before considering the change complete, run:

```bash
make check
```

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

## Public Workflow Documents

The JSON files accepted by:

```bash
azathoth workflow import <FILE>
```

are canonical serialized `WorkflowSpecification` documents.

They are not a separate tutorial or CLI schema.

When workflow serialization changes, checked-in examples and round-trip tests
must remain synchronized with the actual public document representation.

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

## Documentation

Documentation should describe implemented behavior.

Avoid describing planned architecture as though it already exists.

When a feature changes a public subsystem boundary, update the corresponding
package README:

```text
src/azathoth/<subsystem>/README.md
```

When it changes the overall user-facing system, also consider:

```text
README.md

docs/getting-started.md

CONTRIBUTING.md

docs/release-validation.md
```

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
ruff format src tests
ruff check src tests
mypy src
pytest
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

For release hardening, distinguish clearly between:

```text
new feature

and

making existing V1 behavior safer, clearer, or more verifiable
```

The OSS V1 release-hardening phase is intentionally conservative.

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

## Release Validation

Release-level verification has stricter expectations than an individual local
change.

Before declaring an OSS release candidate ready, follow:

[Release Validation](docs/release-validation.md).

## Central Rule

When in doubt:

```text
make the domain explicit

record evidence

keep authority narrow

test the boundary

document what actually exists
```