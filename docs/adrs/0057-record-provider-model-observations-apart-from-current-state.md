# ADR 0057: Record Provider Model Observations Apart From Current State

- Status: Accepted
- Date: 2026-08-25
- Decided in: #63

## Context

Provider catalogs change without notice. Models appear, disappear, change
price, and gain or lose capabilities.

Optimization evidence is only reproducible if Azathoth can later say what a
provider reported about a model at the time the evidence was produced. At the
same time, runtime selection must use what the provider reports now, not what
it reported last week.

Before this decision, discovered provider models existed only for the life of
one process. Nothing durable recorded how a provider's catalog had changed.

## Decision

`ProviderModelObservation` records the complete normalized `ProviderModel` as
observed at one moment, with its own identity and timestamp.

`ProviderModelObserver` coordinates discovery with durable history:

```text
discover model
     │
     ▼
compare fingerprint with the latest observation
     │
     ├── unchanged ──► reuse the latest observation
     │
     └── changed ────► persist a new observation
```

A model's fingerprint covers the provider-reported facts, so an unchanged model
produces no new record, and every record marks a real change.

The observer also rejects discovered models from an unexpected provider, and a
directory that returns the same model identity twice.

Observation history is evidence. It never decides which models are current.

```text
observation history  ≠  current availability
```

## Consequences

### Positive

- Provider catalog changes become durable, inspectable history.
- History grows only when provider facts actually change.
- Current selection stays independent of stale observations.
- A model that disappears keeps its history.

### Negative

- Observation storage grows with provider churn.
- History records what was observed, not what a provider intended, so
  short-lived changes between observations are invisible.

## Alternatives Considered

### Treat the latest observation as the current catalog

Rejected. A model absent from current discovery would still look available.

### Persist every discovery result

Rejected. Unchanged models would bury real changes in duplicate records.
