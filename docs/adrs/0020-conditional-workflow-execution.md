# ADR 0020: Conditional Workflow Execution

- Status: Accepted
- Date: 2026-08-09

## Context

Azathoth workflows are represented as directed acyclic graphs of independently configured workflow steps.

Workflow steps can export structured workflow values, and downstream steps can explicitly reference those values through validated workflow dataflow.

Not every downstream step should necessarily execute.

For example, a workflow may classify a request before selecting an appropriate processing path:

```text
                Classifier
                    │
             classification
                /       \
            "math"     "general"
              │            │
              ▼            ▼
        Math Reasoner  General Reasoner
```

Conditional execution therefore requires a durable representation of eligibility rules that can be validated before execution and evaluated deterministically at runtime.

Conditional routing must preserve the existing workflow architecture:

* workflow topology remains explicit;
* workflow values remain producer-qualified;
* different steps may use different models and tools;
* skipped steps must not fabricate execution evidence;
* dependency-layer semantics must remain deterministic.

Decision

Workflow steps may declare zero or more WorkflowCondition instances.

A workflow condition references a producer-qualified workflow value and declares the value expected for the condition to be satisfied.

```text
WorkflowCondition
├── source
│   ├── producer_step_id
│   └── value name
└── expected value
```

Workflow specifications validate conditions before candidate generation.

Validation ensures that:

* the referenced producer step exists;
* the referenced producer exports the requested workflow value; and
* the producer is upstream of the conditional consumer step.

A workflow step with no conditions is always eligible for execution.

A workflow step with conditions is eligible only when all declared conditions are satisfied.

Multiple conditions therefore use logical AND semantics.

During workflow execution:

* conditions are evaluated against committed workflow values;
* eligible steps execute normally;
* ineligible steps are skipped;
* skipped steps produce no ExecutionResult;
* skipped steps produce no workflow values; and
* skipped steps are still represented in the durable WorkflowRun.

Workflow step execution status is explicitly recorded using WorkflowStepStatus.

A condition referencing an unavailable workflow value evaluates as unsatisfied.

This allows conditional skips to propagate naturally when an upstream conditional branch did not produce a value.

Consequences

Positive

* Workflows can adapt execution based on prior results.
* Conditional routing remains explicit and serializable.
* Invalid condition references fail during workflow validation.
* Workflow execution remains deterministic.
* Skipped steps are distinguishable from executed steps.
* Execution evidence is never fabricated for skipped work.
* Conditional execution composes with existing workflow dependency layers.
* Different conditional branches may independently use different models, tools, or strategies.
* Conditional behavior can be inspected after execution through WorkflowRun.

Negative

* The initial condition model supports equality predicates only.
* Multiple conditions currently use fixed logical AND semantics.
* Skipped upstream branches may cause downstream conditions to become unsatisfied through missing workflow values.

Alternatives Considered

Encode routing directly in strategies

Rejected because routing is workflow orchestration behavior rather than strategy behavior.

Embedding routing inside strategies would obscure workflow topology and make optimization more difficult.

Use shared context events for conditions

Rejected because workflow values already provide an explicit, producer-qualified dataflow model.

Conditions should operate on declared workflow data rather than infer routing state from execution history.

Fabricate execution results for skipped steps

Rejected because a skipped workflow step did not execute.

Recording synthetic execution evidence would make workflow traces misleading and complicate evaluation and optimization.

Introduce a general expression language

Rejected because equality conditions and logical AND semantics provide useful conditional execution without prematurely introducing a workflow expression language.