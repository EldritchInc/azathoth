# ADR 0038: OpenRouter Provider

- Status: Accepted
- Date: 2026-08-16

## Context

Azathoth executes provider-neutral language model requests through the
`LanguageModel` protocol.

A concrete provider implementation is required to execute workflows against
real language models while preserving deterministic testing and provider
independence.

The first production provider should maximize model availability while
minimizing integration complexity.

## Decision

Azathoth introduces `OpenRouterLanguageModel` as its first production language
model provider.

The implementation maps rendered prompts to the OpenRouter chat completion API
and translates provider responses into provider-neutral `ModelResponse`
objects.

Live provider testing is opt-in.

Normal unit tests and continuous integration remain fully deterministic through
mocked HTTP transports.

## Consequences

### Positive

- Azathoth can execute real language model requests.
- Existing provider abstractions remain unchanged.
- Unit and integration tests remain deterministic.
- Live provider verification is explicitly opt-in.
- Future providers can implement the same protocol.

### Negative

- OpenRouter-specific request mapping becomes part of the codebase.
- HTTP becomes a runtime dependency.
- Live integration tests require external credentials.

## Alternatives Considered

### Integrate OpenAI directly

Rejected because OpenRouter provides access to multiple providers through a
single integration.

### Make live tests part of normal CI

Rejected because external services introduce nondeterminism, cost, and
credential management concerns.

### Delay provider integration

Rejected because demonstrating real model execution is the next milestone
toward an end-to-end optimization demo.