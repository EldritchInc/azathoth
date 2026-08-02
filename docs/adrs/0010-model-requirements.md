# ADR 0010: Separate Model Requirements from Model Discovery

- Status: Accepted
- Date: 2026-08-02

## Context

Azathoth optimizes AI workflows by evaluating candidate strategies across
multiple language models.

As the system evolves, strategies should not be tightly coupled to specific
providers or model identifiers. Instead, a strategy should describe the
capabilities required to execute successfully, allowing the optimization
system to determine which concrete models are eligible for evaluation.

Conflating workload requirements with provider discovery would tightly couple
optimization logic to infrastructure concerns and make future provider
integrations, model arbitrage, and capability discovery more difficult.

## Decision

Language-model-backed strategies declare provider-neutral
`ModelRequirements`.

`ModelRequirements` describe the characteristics required from a language
model, including capabilities, supported modalities, context limits, and
optional pricing constraints.

These requirements are translated into immutable `ModelQuery` objects.

`ModelQuery` instances are evaluated against a `ModelCatalog`, which
contains immutable metadata describing the language models available to
Azathoth.

The catalog is responsible only for discovering eligible models.

Selection among eligible models remains the responsibility of future
optimization policies.

## Consequences

### Positive

- Strategies remain independent of specific providers.
- Workload definitions become reusable across providers.
- Provider integrations remain isolated from optimization logic.
- Model discovery and model selection evolve independently.
- Capability-based discovery naturally supports future model arbitrage.
- Experiments can compare multiple eligible models without changing
  strategy definitions.
- Workload requirements remain immutable, serializable, and reproducible.

### Negative

- Introduces additional domain models (`ModelRequirements` and
  `ModelQuery`) with intentionally similar structure.
- Requires an explicit translation step from workload requirements to
  catalog queries.

## Alternatives Considered

### Strategies directly reference model identifiers

Rejected because strategy definitions become tightly coupled to provider
implementations, making experimentation and provider replacement more
difficult.

### Combine `ModelRequirements` and `ModelQuery`

Rejected because they represent different concepts.

`ModelRequirements` describe what a workload needs.

`ModelQuery` describes how a catalog is searched.

Keeping these concepts separate preserves a clear boundary between workload
definition and infrastructure.