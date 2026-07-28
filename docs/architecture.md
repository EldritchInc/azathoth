# Azathoth Architecture

## Purpose

Azathoth empirically discovers which executable strategies produce the best
results for different kinds of context.

A strategy may include:

- a prompt;
- a model;
- retrieval;
- a deterministic tool;
- an information request;
- or a multi-step workflow.

## MVP execution loop

```text
Goal + Context
      |
      v
Select Candidate Strategy
      |
      v
Execute Strategy
      |
      v
Update Structured Context
      |
      v
Evaluate Result
      |
      v
Complete or Select Next Strategy

Every execution step may append structured information to the shared context.

Architectural principles

1. Evaluation is a first-class capability.
2. Context changes are traceable and reproducible.
3. Prompts are strategies, not the entire product.
4. External model and evaluation providers are accessed through interfaces.
5. Optimization decisions must be supported by recorded evidence.
6. Failures should become replayable regression cases.
7. The MVP should remain useful without future autonomous capabilities.

MVP boundaries

The MVP includes:

* structured goals and contexts;
* executable strategies;
* model and prompt comparison;
* configurable evaluation;
* experiment execution;
* context-aware routing;
* regression replay.

The MVP does not include:

* autonomous long-running goals;
* hierarchical goal synthesis;
* self-modifying code;
* autonomous model training;
* unrestricted tool creation.

