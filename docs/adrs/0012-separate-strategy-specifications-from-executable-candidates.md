# ADR 0012: Separate Strategy Specifications from Executable Candidates

## Status

Accepted

## Context

Prompt strategies originally represented executable workloads because they contained a concrete language model implementation.

As Azathoth evolved toward empirical optimization, a single workload needed to be evaluated across multiple language models without duplicating workload definitions.

The architecture therefore required a distinction between:

- describing a workload; and
- executing that workload with a specific language model.

Additionally, generated candidates require stable identities so experimental evidence can be attributed to the correct executable strategy.

## Decision

Introduce immutable `PromptStrategySpec` objects that describe a prompt-backed workload independently of any executable language model.

Candidate generation combines:

- a prompt strategy specification;
- model requirements;
- a model catalog; and
- an executable language model registry

to produce executable `PromptStrategy` instances.

Each generated candidate:

- is bound to exactly one executable language model;
- receives a deterministic identity derived from the specification identifier and model identifier;
- preserves the workload definition while representing an independently executable strategy.

## Consequences

Positive:

- workload definitions become reusable and serializable;
- executable strategies become runtime artifacts;
- one specification can generate multiple empirical candidates;
- candidate identities remain stable across repeated generation;
- experimental evidence can be attributed to specific model-bound strategies;
- future model arbitrage and automatic strategy generation build naturally on this architecture.

Negative:

- candidate generation introduces an additional translation step between specification and execution;
- executable strategies no longer share the same identity as their originating specification.

## Alternatives Considered

### Bind language models directly to specifications

Rejected because specifications would become runtime objects rather than durable workload definitions.

### Reuse specification identities for generated candidates

Rejected because multiple executable strategies would share the same identity, preventing reliable attribution of experimental evidence.

## Result

Azathoth now cleanly separates workload definition from executable strategy generation, allowing a single specification to produce multiple deterministic, model-bound candidates suitable for empirical optimization.