# ADR 0059: Separate Portfolio Selection From Fixed Model Selection

- Status: Accepted
- Date: 2026-08-26
- Decided in: #65

## Context

Prompt steps need two different kinds of model authority.

Experimentation and optimization want Azathoth to choose among legitimate
models and compare them. Production wants one exact model, chosen
deliberately, that does not change because the portfolio did.

A single "model" field cannot carry both meanings without one silently
becoming the other.

## Decision

Every `PromptStrategySpec` carries an explicit `ModelSelection`:

```text
ModelSelection
├── PortfolioModelSelection
└── FixedModelSelection
```

`PortfolioModelSelection` holds `ModelRequirements`. Azathoth may choose any
model that is authorized, current, satisfies the requirements and has an
executable implementation.

`FixedModelSelection` names one exact `provider` and `model`. Its identifier,
`provider/model`, is derived from those two fields rather than stored, so it
cannot drift.

Fixed selection never falls back:

```text
FixedModelSelection
        │
        ├── in the current catalog and executable ──► candidate
        │
        └── otherwise ───────────────────────────────► no candidate
```

It does not search the portfolio for something similar, choose a cheaper
model, or reinterpret itself as a portfolio selection. Any substitution must
be explicit policy owned elsewhere (see ADR 0063).

## Consequences

### Positive

- The authority behind every prompt step's model is visible in its
  specification.
- Optimization can explore portfolio selections freely.
- Fixed intent stays exact.

### Negative

- A fixed step whose model disappears produces no candidate, and fails
  explicitly rather than degrading.

## Alternatives Considered

### Fall back from a fixed model to the portfolio

Rejected. A deliberate choice would quietly become a different one.

### One selection type with an optional exact model

Rejected. The two authority models would be distinguished by the presence of
a field rather than by type.
