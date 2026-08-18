# ADR 0009: Introduce an Immutable Model Catalog

- **Status:** Accepted
- **Date:** 2026-08-01

## Context

Azathoth's purpose is to empirically optimize AI workflows rather than hard-code decisions about prompts, models, tools, or execution paths.

As support for language models was introduced, the system required a provider-neutral way to represent the available models before any optimization could occur.

Without a dedicated abstraction, strategies or optimization logic would need to embed provider-specific knowledge, creating tight coupling between workflow optimization and the underlying AI providers.

Additionally, future optimization will need to answer questions such as:

- Which models support structured output?
- Which models have sufficient context windows?
- Which models support tool use?
- Which models meet a particular pricing constraint?
- Which models are even eligible for a particular workflow?

These are discovery questions, not optimization questions.

The architecture therefore requires an explicit separation between:

- discovering candidate models
- executing those models
- evaluating their performance
- selecting the optimal strategy

## Decision

Azathoth represents available language models using immutable metadata stored within a `ModelCatalog`.

Each model is represented by a `ModelMetadata` object describing characteristics such as:

- provider
- model identifier
- supported capabilities
- supported modalities
- context window
- output limits
- pricing information

The `ModelCatalog` provides a reproducible inventory of configured models and supports deterministic lookup and discovery.

Model discovery requirements are represented independently using immutable `ModelQuery` objects.

A `ModelQuery` describes the capabilities and constraints required for a workload and is evaluated against catalog entries to determine the eligible candidate models.

The catalog is intentionally limited to discovery and does not perform routing, ranking, or optimization.

## Consequences

### Positive

- Provider-specific knowledge remains isolated from optimization logic.
- Model discovery becomes deterministic and reproducible.
- Capability filtering is implemented independently of optimization policy.
- Experiments can operate over well-defined candidate model sets.
- Model metadata can evolve independently of execution metrics.
- The catalog can later be populated from configuration files, provider APIs, or external registries without changing optimization components.

### Negative

- Additional domain models are required before execution can occur.
- Discovery introduces another architectural layer that must be maintained.
- Provider integrations must translate provider-specific information into `ModelMetadata`.

## Alternatives Considered

### Strategies reference provider implementations directly

This would tightly couple optimization logic to provider-specific implementations and make adding or replacing providers increasingly difficult.

Rejected.

### Perform capability filtering inside optimization

This mixes model discovery with optimization policy and makes the optimization engine responsible for provider-specific concerns.

Rejected.

### Maintain provider-specific catalogs

This would duplicate discovery logic across providers and prevent a uniform optimization pipeline.

Rejected.

## Future Direction

Future optimization components may use the catalog to:

- discover eligible candidate models
- generate experiment candidates
- compare providers
- optimize for quality, latency, and cost
- automatically evaluate newly available models

The catalog intentionally does not decide which model should be selected.

Selection remains the responsibility of the optimization engine, allowing discovery and optimization to evolve independently.