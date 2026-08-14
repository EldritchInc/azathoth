# ADR 0033: Durable Tool Definitions

- Status: Accepted
- Date: 2026-08-14

## Context

Azathoth workflows will increasingly rely on reusable capabilities beyond language
models.

Representing tools as Python functions tightly couples capability definitions to
implementation details and execution environments.

Future optimization systems should reason about durable capabilities, independently
of how those capabilities are executed or persisted.

Tool definitions should therefore establish stable contracts describing what a
capability accepts and produces without requiring a specific runtime or
implementation.

## Decision

Tools are represented as immutable, versioned capability definitions.

A tool definition packages:

- tool identity;
- name;
- description;
- version;
- input contract; and
- output contract.

Tool verification is represented independently using immutable tool test cases.

Executable implementations are represented independently using immutable tool
implementations.

Tool catalogs provide deterministic discovery of tool definitions without
introducing execution behavior, persistence, or optimization policy.

Tool definitions remain independent of implementation language, execution
environment, and storage mechanism.

## Consequences

### Positive

- Capability contracts remain stable as implementations evolve.
- Multiple implementations may satisfy the same capability.
- Tool discovery remains deterministic.
- Durable capabilities become independent of runtime environments.
- Future persistence mechanisms can evolve independently of the tool model.
- Automatic tool generation and verification become natural extensions of the
  architecture.

### Negative

- Additional domain models become part of the public API.
- Tool execution requires additional layers beyond the capability model.
- Catalogs currently provide deterministic discovery only.

## Alternatives Considered

### Represent tools as Python functions

Rejected because executable code does not provide durable capability contracts and
cannot naturally support multiple implementations.

### Couple tool definitions directly to persistence

Rejected because persistence mechanisms should remain interchangeable and should
not define the domain model.

### Couple tool definitions directly to execution

Rejected because execution policies evolve independently from capability
definitions.

Separating capability, implementation, verification, discovery, persistence, and
execution establishes a stable foundation for future optimization systems.