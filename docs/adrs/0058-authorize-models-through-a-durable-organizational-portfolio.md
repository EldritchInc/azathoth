# ADR 0058: Authorize Models Through a Durable Organizational Portfolio

- Status: Accepted
- Date: 2026-08-25
- Decided in: #64

## Context

A provider exposing a model does not mean an organization wants Azathoth to use
it. Organizations restrict models for cost, data-handling, contractual, and
quality reasons.

Before this decision, any model in the current catalog that satisfied a
step's requirements was eligible for selection. Availability and permission
were the same thing.

## Decision

`ModelPortfolio` is the ordered set of models an organization has explicitly
authorized for Azathoth to select. Each `ModelPortfolioEntry` names exactly one
provider-qualified model.

The portfolio is durable policy, persisted through
`ModelPortfolioRepository` (`InMemoryModelPortfolioRepository` and
`SQLiteModelPortfolioRepository`) and reconstructed by `ModelPortfolioLoader`.

Availability and authorization are composed explicitly by
`model_catalog_for_portfolio`:

```text
ModelCatalog (current)  ∩  ModelPortfolio (authorized)
        │
        ▼
ModelCatalog (authorized and current, in portfolio order)
```

Authorized models absent from the current catalog are omitted. Current models
absent from the portfolio are never added.

The CLI exposes this as `model authorize`, `model deauthorize` and
`model portfolio`. A model must be currently available to be newly
authorized; otherwise the command fails with:

```text
Model '<IDENTIFIER>' is not currently available.
```

Deauthorizing a model removes the permission without claiming the provider
model stopped existing.

## Consequences

### Positive

- Availability and authorization are separate, inspectable facts.
- Organizational policy survives process restarts and provider churn.
- Portfolio order gives selection a deterministic preference.

### Negative

- A new provider model is unusable until someone authorizes it.
- An authorized model that disappears silently drops out of selection until it
  returns.

## Alternatives Considered

### Configure allowed models in environment variables

Rejected. Authorization is durable policy, not process configuration.

### Allow every current model by default

Rejected. Permission would follow whatever a provider happens to publish.
