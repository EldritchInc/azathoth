# ADR 0034: Tool Execution

- Status: Accepted
- Date: 2026-08-14

## Context

Tool definitions describe durable capabilities independently of execution
environments.

Tool implementations describe executable realizations of those capabilities.

Future optimization systems, benchmarking pipelines, and synthesized tool
generation require deterministic evidence that implementations satisfy their
contracts.

Execution should remain independent from verification so that multiple
verification strategies may evolve without changing execution semantics.

## Decision

Azathoth introduces deterministic tool execution.

Tool execution consists of:

- executable tool implementations;
- asynchronous tool executor protocols;
- Python tool execution;
- durable tool verification; and
- immutable tool verification results.

Tool executors execute implementations and return structured outputs.

Tool verifiers execute durable tool test cases using tool executors and compare
actual outputs against expected outputs.

Verification remains deterministic.

Execution does not perform optimization, ranking, or heuristic evaluation.

## Consequences

### Positive

- Tool execution is separated from verification.
- Tool verification produces durable evidence of correctness.
- Multiple executor implementations may coexist.
- Future runtimes can be introduced without changing verification.
- Future verification strategies can evolve independently of execution.
- Tool execution remains deterministic and fully testable.

### Negative

- Additional execution and verification models become part of the public API.
- Trusted Python execution is currently performed in-process.
- Additional runtimes require future executor implementations.

## Alternatives Considered

### Execute tools directly from tool definitions

Rejected because capability definitions should remain independent of execution.

### Combine execution and verification

Rejected because execution and verification evolve independently.

Separating these responsibilities allows multiple verification policies to share
the same execution substrate.

### Store verification inside tool implementations

Rejected because verification represents evidence produced by execution rather
than implementation metadata.