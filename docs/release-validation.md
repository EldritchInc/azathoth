# Release Validation

This document defines the OSS V1 release-validation contract.

It answers one question:

> What must be true before the repository can be considered ready to ship?

Release validation is intentionally stricter than demonstrating that one
feature works.

The release must prove that the documented system is internally consistent,
deterministic under normal test conditions, installable through its supported
development path, and operable through its public boundaries.

## Release Philosophy

Azathoth separates:

```text
feature completeness

from

release readiness
```

The OSS V1 feature surface is frozen during release hardening.

Release validation should therefore find and correct:

- broken public journeys;
- stale documentation;
- packaging problems;
- inconsistent command behavior;
- missing lifecycle coverage;
- type or lint regressions;
- accidental nondeterminism;
- and contradictions between documented and implemented architecture.

It should not become an excuse to introduce unrelated capabilities.

## Required Deterministic Gate

A release candidate must pass the complete deterministic repository gate:

```bash
make check
```

Individual components can also be run directly:

```bash
ruff format --check src tests
ruff check src tests
mypy src
pytest
```

When preparing changes locally, formatting may be applied with:

```bash
ruff format src tests
```

The release branch itself should already be formatted before validation.

## What the Deterministic Gate Means

Normal release validation must not require:

```text
network access

OpenRouter availability

provider credentials

paid model execution

mutable external service state
```

Provider behavior used by normal automated tests should remain deterministic
through controlled implementations or mocked transports.

This ensures that:

```text
green repository
```

means:

```text
green Azathoth implementation
```

rather than:

```text
an external API happened to cooperate
```

## Live OpenRouter Verification

Live provider verification exists as a separate opt-in layer.

It can be enabled with:

```bash
export AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1
export OPENROUTER_API_KEY='YOUR_OPENROUTER_API_KEY'
```

Some live tests require:

```bash
export OPENROUTER_TEST_MODEL='<provider-native-model-id>'
```

and multi-model verification may require:

```bash
export OPENROUTER_TEST_MODELS='<model-a>,<model-b>'
```

These tests verify real integration behavior such as:

- OpenRouter language-model execution;
- current model discovery;
- durable provider observation;
- workflow execution against a live model; and
- multi-model registry execution.

They may consume API credits.

They may also be affected by:

- provider downtime;
- provider model changes;
- alias resolution;
- rate limits;
- external latency; and
- provider response drift.

Therefore live verification is not part of the deterministic `make check`
contract.

A release may intentionally perform it as additional confidence before
publication.

## Documentation Validation

Before release, confirm the root project story matches the implementation.

Review:

```text
README.md
docs/getting-started.md
CONTRIBUTING.md
docs/release-validation.md
```

Then review subsystem documentation:

```text
src/azathoth/cli/README.md
src/azathoth/context/README.md
src/azathoth/evaluation/README.md
src/azathoth/execution/README.md
src/azathoth/goals/README.md
src/azathoth/optimization/README.md
src/azathoth/prompting/README.md
src/azathoth/providers/README.md
src/azathoth/runtime/README.md
src/azathoth/strategies/README.md
src/azathoth/tools/README.md
src/azathoth/workflows/README.md
```

Documentation must not describe a planned capability as implemented.

Documentation must also not describe removed intermediate architecture as
current behavior.

## Architecture Validation

The release should preserve these V1 invariants.

### Workflow identity

```text
WorkflowSpecification
    durable intent

WorkflowCandidate
    executable realization

WorkflowRun
    empirical evidence
```

These identities must not be collapsed.

### Model ontology

```text
ProviderModel
    current provider truth

ProviderModelObservation
    historical observation

ModelCatalog
    current normalized metadata

ModelPortfolio
    organizational authorization

LanguageModelRegistry
    executable implementations
```

Availability, history, authorization, metadata, and execution remain separate.

### Production ontology

```text
WorkflowProductionState
    current execution authority

WorkflowProductionRevision
    immutable audit history

ProductionInvocation
    external call identity

WorkflowRun
    execution evidence
```

Production invocation must execute current production state.

It must not infer authority from the newest revision.

### Optimization authority

```text
optimization
    proposes and evaluates candidates

promotion
    changes production
```

Optimization must not silently deploy.

### Persistence

Repositories should store domain state.

They must not become hidden orchestration or provider-policy layers.

## Public CLI Validation

Confirm the installed CLI exposes the expected V1 command families:

```text
azathoth
│
├── workflow
│   ├── import
│   ├── list
│   ├── show
│   ├── run
│   ├── optimize
│   ├── promote
│   └── invoke
│
└── model
    ├── list
    ├── show
    ├── authorize
    ├── deauthorize
    └── portfolio
```

Check:

```bash
azathoth --help
azathoth workflow --help
azathoth model --help
```

Help and version commands should not require runtime bootstrap, a database, or
provider credentials.

## Canonical Workflow Example

The release contains:

```text
examples/workflows/simple-prompt.json
```

This file must remain valid canonical workflow serialization.

The test suite should prove:

```text
decode(example)
    =
expected WorkflowSpecification
```

and:

```text
encode(expected WorkflowSpecification)
    =
example
```

A user-visible example that has drifted from the actual serialization contract
is a release failure.

## Provider-Free Fresh-User Boundary

The following journey must remain provider-independent:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json

azathoth workflow list

azathoth workflow show \
    11111111-1111-1111-1111-111111111111
```

It must not require:

```text
OPENROUTER_API_KEY
```

This proves users can ingest and inspect durable workflow intent before
configuring execution.

## Model Operator Boundary

With current provider state configured, the operator lifecycle must preserve:

```text
current model
    │
    ▼
authorize
    │
    ▼
durable ModelPortfolio
    │
    ▼
runtime reconstruction
    │
    ▼
authorization remains visible
```

Deauthorization must remove authorization without pretending the provider model
ceased to exist.

A model that is no longer currently available must not be newly authorized
merely because it was previously known.

## Configured Execution Boundary

`workflow run` must continue to mean:

```text
configured WorkflowSpecification
        │
        ▼
runtime candidate generation
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRun
```

It must not silently execute active production state.

## Optimization Boundary

`workflow optimize` must continue to perform empirical candidate search using
explicit expected output and scoring targets.

It must not modify:

```text
WorkflowProductionState
```

as a side effect.

## Promotion Boundary

`workflow promote` must explicitly materialize a configured candidate into:

```text
WorkflowProductionState
```

and record:

```text
WorkflowProductionRevision
```

Promotion state and revision should describe the same promoted behavior while
retaining their different authority semantics.

## Production Invocation Boundary

`workflow invoke` must execute:

```text
runtime.production_state(workflow_id)
```

and persist:

```text
ProductionInvocation

WorkflowRun

ProductionInvocationRun association
```

An undeployed workflow must fail explicitly.

It must not silently execute configured workflow behavior.

## Runtime Reconstruction

Release validation should continue to prove that durable configuration survives
process/runtime reconstruction.

Examples include:

- workflow specifications;
- model portfolio authorization;
- provider observations;
- tool definitions and implementations;
- production state;
- production revisions;
- workflow runs;
- and production invocation evidence.

Runtime reconstruction should create a new process-local composition snapshot.

Previously constructed runtime objects should not mutate because durable state
changed afterward.

## Secrets

Provider credentials are process-local configuration.

They must not become part of durable workflow documents.

Tests should continue to ensure secret values are not exposed through normal
configuration representation or serialization.

## Failure Semantics

The public CLI should continue to distinguish success from expected failure
through process status.

General expectations are:

```text
successful command
    exit 0

expected command/domain failure
    nonzero exit
```

Operator-facing failures should be emitted to standard error.

Successful results should be emitted to standard output.

## Release Acceptance Test

The repository should contain one focused deterministic acceptance test that
proves the public V1 lifecycle across the major boundaries.

That test should not attempt to duplicate every subsystem test.

Its purpose is to answer:

> Can the major pieces of the documented OSS V1 lifecycle still work together?

The acceptance path should cover, with deterministic provider behavior:

```text
workflow configuration
        │
        ▼
model availability
        │
        ▼
model authorization
        │
        ▼
configured execution
        │
        ▼
empirical optimization
        │
        ▼
explicit promotion
        │
        ▼
production invocation
        │
        ▼
durable evidence
```

This acceptance test remains part of the deterministic test suite.

It must not use the live OpenRouter service.

## Release Candidate Checklist

A release candidate is ready for final review when all of the following are
true:

```text
[ ] repository formatting is clean

[ ] linting passes

[ ] mypy passes

[ ] deterministic pytest suite passes

[ ] make check passes

[ ] canonical workflow example round-trips

[ ] installed CLI help/version work

[ ] provider-free import/list/show journey works

[ ] model authorization survives reconstruction

[ ] configured workflow execution works

[ ] empirical optimization works

[ ] optimization does not promote

[ ] explicit promotion persists production state

[ ] promotion records immutable revision history

[ ] production invocation uses active state

[ ] production invocation persists durable evidence

[ ] undeployed production invocation fails explicitly

[ ] root documentation matches implemented behavior

[ ] subsystem documentation matches implemented behavior

[ ] public examples match current serialization

[ ] no provider credentials are committed

[ ] optional live-provider verification is handled separately
```

## Optional Pre-Release Live Check

When desired, perform live OpenRouter verification only after the deterministic
release candidate is green.

Conceptually:

```text
deterministic release gate
        │
        ▼
green
        │
        ▼
optional live provider verification
```

Never reverse those responsibilities.

Live provider success cannot compensate for a failing deterministic gate.

## What Release Ready Means

For OSS V1, release ready means:

```text
the existing architecture is understandable

the documented public journey works

the deterministic repository is green

durable boundaries survive reconstruction

production authority remains explicit

optimization remains empirical

provider integration is independently verifiable
```

It does not mean every future convenience feature exists.

That distinction protects the V1 feature freeze.

## Central Release Rule

A release should make one claim confidently:

> The behavior Azathoth documents is the behavior Azathoth actually ships.