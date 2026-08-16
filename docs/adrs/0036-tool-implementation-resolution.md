# ADR 0036: Tool Implementation Resolution

- Status: Accepted
- Date: 2026-08-16

## Context

Tool definitions describe durable capability contracts.

Executable behavior is provided by tool implementations rather than capability
definitions.

Multiple implementations may satisfy the same capability contract across
different runtimes, implementation versions, or execution environments.

Workflow execution requires deterministic selection of executable
implementations while remaining independent of optimization policy.

## Decision

Azathoth introduces immutable implementation catalogs and deterministic
implementation resolution.

Implementation catalogs provide inventories of executable tool
implementations.

Implementation resolvers map capability definitions to executable
implementations.

Runtime constraints are evaluated only during implementation resolution.

Capability resolution and implementation resolution remain separate
architectural responsibilities.

## Consequences

### Positive

- Capability definitions remain independent of execution environments.
- Runtime selection is separated from capability resolution.
- Multiple implementations may coexist for the same capability.
- Implementation resolution remains deterministic.
- Future optimization systems can rank implementations without changing
  deterministic resolution.

### Negative

- Additional implementation models become part of the public API.
- Resolution currently performs exact constraint matching only.
- Ranking and optimization remain future responsibilities.

## Alternatives Considered

### Store implementations directly in tool definitions

Rejected because executable implementations evolve independently of capability
contracts.

### Resolve runtime during capability resolution

Rejected because runtime is an implementation concern rather than a capability
concern.

### Select a preferred implementation automatically

Rejected because implementation preference belongs to optimization policy rather
than deterministic resolution.