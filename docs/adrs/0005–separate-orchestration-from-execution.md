Title:
Separate Optimization Orchestration from Execution

Decision

Introduce OptimizationRunner as an orchestration layer.

StrategyExecutor executes strategies.

Evaluators score outputs.

OptimizationRunner coordinates both.

Rationale

Execution should not know how results are evaluated.

Evaluation should not know how strategies execute.

Optimization should consume both without coupling.

Consequences

- easier testing
- dependency injection
- future optimizer implementations
- cleaner separation of concerns