# ADR 0015: Represent Workflows as Dependency Graphs

- Status: Accepted
- Date: 2026-08-06

## Context

Azathoth represents AI systems as workflows composed of independently configured workflow steps.

As workflows become more sophisticated, simple sequential ordering is no longer sufficient.

Many AI systems naturally contain independent work that can execute concurrently, while other steps must wait until prerequisite work has completed.

The workflow model therefore requires an explicit representation of dependency relationships without introducing runtime execution behavior.

## Decision

Workflow step specifications may declare dependencies on other workflow steps.

A workflow therefore represents a directed acyclic graph (DAG) rather than a simple ordered list.

Workflow specifications validate that:

- every dependency references another step in the same workflow;
- workflow steps cannot depend on themselves;
- dependency declarations are unique; and
- dependency graphs are acyclic.

Workflow specifications expose deterministic execution layers derived from the dependency graph.

Each execution layer contains workflow steps whose dependencies have already been satisfied.

Execution layers preserve the declared ordering of independent workflow steps while exposing opportunities for future concurrent execution.

Workflow specifications remain durable configuration and contain no runtime scheduling or execution behavior.

## Consequences

### Positive

- Workflow topology is represented explicitly.
- Independent workflow steps can be identified deterministically.
- Future workflow runners can execute dependency layers without redefining workflow structure.
- Parallel execution opportunities are preserved.
- Workflow planning remains deterministic and reproducible.
- Individual workflow steps continue to own their own model requirements and execution configuration.

### Negative

- Workflow planning introduces additional validation complexity during construction.

## Alternatives Considered

### Represent workflows as ordered lists

Rejected because ordering alone cannot represent independent work or synchronization points.

### Perform dependency validation during execution

Rejected because invalid workflow topology should be rejected before execution begins.

### Introduce a workflow scheduler

Rejected because scheduling is a runtime concern.

Workflow specifications intentionally remain execution-independent.