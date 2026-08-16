# ADR 0037: Model Request Execution

- Status: Accepted
- Date: 2026-08-16

## Context

Language model providers expose a protocol for executing rendered prompts.

Future provider integrations will require durable request models supporting
provider-neutral execution parameters.

Introducing provider-specific execution semantics directly into the language
model protocol would unnecessarily couple execution to future network
implementations.

A provider-neutral execution boundary enables future providers to evolve without
changing higher-level workflow execution.

## Decision

Azathoth introduces immutable model requests and provider-neutral model
execution.

Model requests package rendered prompts together with future execution
parameters.

Model executors bridge durable requests to existing language model providers.

Unsupported execution controls are rejected explicitly rather than ignored.

Language model providers continue to execute rendered prompts until request-aware
providers are introduced.

## Consequences

### Positive

- Durable request models become part of the public API.
- Execution remains deterministic.
- Existing language model implementations remain compatible.
- Future providers can adopt request-aware execution incrementally.
- Unsupported request controls fail explicitly.

### Negative

- Request execution currently supports prompt-only execution.
- Additional execution layers become part of the architecture.
- Advanced generation controls remain unavailable until provider-specific
  implementations exist.

## Alternatives Considered

### Replace the language model protocol immediately

Rejected because doing so would unnecessarily break existing deterministic
providers and workflow execution.

### Ignore unsupported request controls

Rejected because silently discarding execution parameters would produce
incorrect behavior and make future debugging significantly more difficult.

### Introduce provider-specific request models

Rejected because request models should remain independent of individual provider
implementations.