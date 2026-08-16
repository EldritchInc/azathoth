# ADR 0039: OpenRouter Workflow Execution

- Status: Accepted
- Date: 2026-08-16

## Context

Azathoth provides provider-neutral workflow execution through immutable workflow
specifications, candidate generation, and executable language model bindings.

The provider layer already supports production language model execution through
OpenRouter.

The workflow layer should execute against production language models without
introducing provider-specific logic into workflow execution.

Testing must remain deterministic and inexpensive while still allowing
verification against real language models.

## Decision

Workflow execution now supports production language models through the existing
provider abstraction.

Workflow candidates continue to bind provider-neutral model identifiers through
the language model registry.

Production execution is verified through:

- deterministic end-to-end workflow tests using mocked HTTP transports; and
- opt-in live workflow smoke tests executed against OpenRouter.

Live workflow execution is never part of normal development or continuous
integration.

Execution remains deterministic unless explicitly requested.

## Consequences

### Positive

- Workflows execute against production language models.
- Workflow execution remains provider neutral.
- Existing workflow abstractions remain unchanged.
- Normal development remains deterministic.
- Live verification remains explicitly opt-in.
- Future providers automatically participate through the existing abstraction.

### Negative

- Live workflow verification requires external credentials.
- Production providers may expose alias resolution and provider-specific
  execution metadata.

## Alternatives Considered

### Execute providers directly from workflows

Rejected because workflow execution should remain independent from provider
implementations.

### Make live workflow tests part of continuous integration

Rejected because external services introduce nondeterminism, credentials, and
usage costs.

### Delay production workflow execution

Rejected because demonstrating real workflow execution is a prerequisite for
provider comparison, routing, benchmarking, and optimization.