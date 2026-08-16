# ADR 0035: Tool Requirements

- Status: Accepted
- Date: 2026-08-16

## Context

Workflows should express the capabilities they require rather than depending on
specific tool identifiers.

Tool definitions describe durable capabilities independently of executable
implementations.

As the number of available tools grows, workflow execution requires a
deterministic mechanism for resolving capability requirements into candidate tool
definitions.

Requirement matching should remain objective and independent of optimization,
ranking, and execution policy.

## Decision

Azathoth introduces durable tool requirements and deterministic requirement
resolution.

Tool requirements describe the capabilities needed by higher-level systems.

Tool matchers determine whether a tool definition satisfies a requirement.

Tool resolvers coordinate immutable tool catalogs and deterministic matching to
produce candidate tool definitions.

Resolution preserves catalog ordering and introduces no ranking, optimization, or
heuristics.

## Consequences

### Positive

- Workflows depend on capabilities rather than identifiers.
- Requirement resolution remains deterministic.
- Matching policy is separated from catalog storage.
- Multiple matching strategies can evolve independently.
- Future optimization systems can rank candidate definitions without changing
  requirement resolution.

### Negative

- Additional domain models become part of the public API.
- Resolution currently operates on capability definitions only.
- Runtime selection remains a future responsibility of implementation
  resolution.

## Alternatives Considered

### Resolve tools directly from the catalog

Rejected because catalogs should remain immutable inventories rather than
containing matching policy.

### Couple matching to workflow execution

Rejected because capability resolution should remain reusable independently of
workflows.

### Introduce heuristic or semantic matching

Rejected because deterministic exact matching provides a stable architectural
foundation for future optimization systems.