# Architecture Decision Records

Each record explains one architectural decision: the context it was made in,
what was decided, and its consequences. Records are never rewritten to match
later decisions. A record whose decision was later changed says so in its
status line and names the record that changed it.

Every record starts with the same header:

```text
# ADR <NUMBER>: <TITLE>

- Status: Accepted
- Date: <YYYY-MM-DD>
```

Records written after the decision they describe add a line naming the pull
requests that made it:

```text
- Decided in: #<PR>, #<PR>
```

## Records

- [ADR 0001: Represent context changes as events](0001-structured-context-events.md)
- [ADR 0002: Use immutable domain models](0002-immutable-domain-models.md)
- [ADR 0003: Separate strategy behavior from execution orchestration](0003-separate-strategy-execution.md)
- [ADR 0004: Make Evaluation a First-Class Domain Concept](0004-make-evaluation-a-first-class-domain-concept.md)
- [ADR 0005: Separate Optimization Orchestration from Execution](0005-separate-orchestration-from-execution.md)
- [ADR 0006: Aggregate experiment evidence by strategy](0006-aggregate-experiment-evidence-by-strategy.md)
- [ADR 0007: Separate experiment execution from strategy ranking](0007-separate-experiment-execution-from-ranking.md)
- [ADR 0008: Separate provider responses from execution metrics](0008-separate-provider-responses-from-execution-metrics.md)
- [ADR 0009: Introduce an Immutable Model Catalog](0009-model-catalog.md)
- [ADR 0010: Separate Model Requirements from Model Discovery](0010-model-requirements.md)
- [ADR 0011: Separate Strategy Specifications from Executable Strategies](0011-separate-strategy-specifications-from-executable-strategies.md)
- [ADR 0012: Separate Strategy Specifications from Executable Candidates](0012-separate-strategy-specifications-from-executable-candidates.md)
- [ADR 0013: Centralize Validated Prompt Execution](0013-centralized-prompt-execution.md)
- [ADR 0014: Represent Workflows as Durable Specifications](0014-workflow-specifications.md)
- [ADR 0015: Represent Workflows as Dependency Graphs](0015-workflow-dependency-graphs.md)
- [ADR 0016: Generate Executable Workflow Candidates](0016-workflow-candidates.md)
- [ADR 0017: Execute Workflows by Dependency Layers](0017-execute-workflows-by-dependency-layers.md)
- [ADR 0018: Declare and Record Workflow Values](0018-declare-and-record-workflow-values.md)
- [ADR 0019: Explicit Workflow Value Dataflow](0019-workflow-value-dataflow.md)
- [ADR 0020: Conditional Workflow Execution](0020-conditional-workflow-execution.md)
- [ADR 0021: Workflow Condition Operators](0021-workflow-condition-operators.md)
- [ADR 0022: Workflow Retry Policies](0022-workflow-retry-policies.md)
- [ADR 0023: Workflow Step Attempt History](0023-workflow-step-attempt-history.md)
- [ADR 0024: Workflow Failure Policies](0024-workflow-failure-policies.md)
- [ADR 0025: Workflow Execution Statistics](0025-workflow-execution-statistics.md)
- [ADR 0026: Workflow Reliability Metrics](0026-workflow-reliability-metrics.md)
- [ADR 0027: Workflow Evaluation](0027-workflow-evaluation.md)
- [ADR 0028: Workflow Scorecards](0028-workflow-scorecards.md)
- [ADR 0029: Workflow Ranking](0029-workflow-ranking.md)
- [ADR 0030: Workflow Experiments](0030-workflow-experiments.md)
- [ADR 0031: Workflow Optimization Boundary](0031-workflow-optimization-boundary.md)
- [ADR 0032: Workflow Optimization Sessions](0032-workflow-optimization-session.md)
- [ADR 0033: Durable Tool Definitions](0033-durable-tool-definitions.md)
- [ADR 0034: Tool Execution](0034-tool-execution.md)
- [ADR 0035: Tool Requirements](0035-tool-requirements.md)
- [ADR 0036: Tool Implementation Resolution](0036-tool-implementation-resolution.md)
- [ADR 0037: Model Request Execution](0037-model-request-execution.md)
- [ADR 0038: OpenRouter Provider](0038-openrouter-provider.md)
- [ADR 0039: OpenRouter Workflow Execution](0039-openrouter-workflow-execution.md)
- [ADR 0040: Workflow Benchmarks](0040-workflow-benchmarks.md)
- [ADR 0041: Persistent Tool Repository](0041-persistent-tool-repository.md)
- [ADR 0042: Tool-Backed Workflow Steps](0042-tool-backed-workflow-steps.md)
- [ADR 0043: Persist Workflow Specifications, Not Runtime Candidates](0043-persist-workflow-specifications-not-runtime-candidates.md)
- [ADR 0044: Persist Execution Evidence Separately From Later Judgments](0044-workflow-evidence-persistence.md)
- [ADR 0045: Associate Durable Evaluations With Workflow Runs](0045-durable-workflow-evaluations.md)
- [ADR 0046: Persist Workflow Experiment Provenance](0046-durable-workflow-experiments.md)
- [ADR 0047: Assemble Multi-Model Provider Runtimes](0047-multi-model-provider-runtime.md)
- [ADR 0048: Persist Configured Model Metadata](0048-durable-model-catalogs.md)
- [ADR 0049: Persist Reusable Benchmark Datasets](0049-durable-benchmark-datasets.md)
- [ADR 0050: Persist Reusable Goals](0050-durable-goals.md)
- [ADR 0051: Provide Reference Model Substitution Optimization](0051-reference-model-substitution-optimizer.md)
- [ADR 0052: Introduce a Process-Local Runtime Composition Boundary](0052-runtime-composition.md)
- [ADR 0053: Introduce the Azathoth Command-Line Application](0053-command-line-application.md)
- [ADR 0054: Add Workflow Inspection Commands](0054-workflow-inspection-commands.md)
- [ADR 0055: Support Portable Workflow JSON Import](0055-workflow-json-import.md)
- [ADR 0056: Execute Configured Workflows From the CLI](0056-cli-workflow-execution.md)
- [ADR 0057: Record Provider Model Observations Apart From Current State](0057-record-provider-model-observations-apart-from-current-state.md)
- [ADR 0058: Authorize Models Through a Durable Organizational Portfolio](0058-authorize-models-through-a-durable-organizational-portfolio.md)
- [ADR 0059: Separate Portfolio Selection From Fixed Model Selection](0059-separate-portfolio-selection-from-fixed-model-selection.md)
- [ADR 0060: Build Runtime Model Catalogs From Current Provider State](0060-build-runtime-model-catalogs-from-current-provider-state.md)
- [ADR 0061: Track Candidate Identity Through Optimization](0061-track-candidate-identity-through-optimization.md)
- [ADR 0062: Promote Explicitly Into Durable Production State](0062-promote-explicitly-into-durable-production-state.md)
- [ADR 0063: Resolve Production Models From a Fixed Primary and Ordered Substitutes](0063-resolve-production-models-from-a-fixed-primary-and-ordered-substitutes.md)
- [ADR 0064: Keep Production Revisions as Audit History, Not Authority](0064-keep-production-revisions-as-audit-history-not-authority.md)
- [ADR 0065: Invoke Production Through Durable Invocations and Declared Emissions](0065-invoke-production-through-durable-invocations-and-declared-emissions.md)
- [ADR 0066: Keep Optimizing When a Candidate Fails to Execute](0066-keep-optimizing-when-a-candidate-fails-to-execute.md)
- [ADR 0067: Deliver External Input Through One Canonical Event](0067-deliver-external-input-through-one-canonical-event.md)
- [ADR 0068: Persist Every Configured Run, With Feedback as Separate Evidence](0068-persist-every-configured-run-with-feedback-as-separate-evidence.md)
- [ADR 0069: Persist Optimization Evidence for Inspection](0069-persist-optimization-evidence-for-inspection.md)
- [ADR 0070: Compare Outcomes Beyond Exact Equality](0070-compare-outcomes-beyond-exact-equality.md)
- [ADR 0071: Declare Each Workflow's Result](0071-declare-each-workflows-result.md)
- [ADR 0072: Optimize Workflows Against Benchmarks](0072-optimize-workflows-against-benchmarks.md)
- [ADR 0073: Judge Failed Runs by Their Result First](0073-judge-failed-runs-by-their-result-first.md)
- [ADR 0074: Judge Semantic Cases With a Durable Judge Rotation](0074-judge-semantic-cases-with-a-durable-judge-rotation.md)
- [ADR 0075: Save Benchmark Executions](0075-save-benchmark-executions.md)
- [ADR 0076: Import Append-Only Revisions Identified by Content Digests](0076-import-append-only-revisions-identified-by-content-digests.md)
- [ADR 0077: Keep Content Digests Stable When Optional Fields Are Added](0077-keep-content-digests-stable-when-optional-fields-are-added.md)
- [ADR 0078: Dispatch Tools by Runtime, and Run Process Tools](0078-dispatch-tools-by-runtime-and-run-process-tools.md)
- [ADR 0079: Run the Steps of a Dependency Layer Concurrently](0079-run-the-steps-of-a-dependency-layer-concurrently.md)
- [ADR 0080: Resolve Redundant Producers by Name](0080-resolve-redundant-producers-by-name.md)
- [ADR 0081: Record Unresolved Inputs and Unresolvable Outputs as Step Failures](0081-record-unresolved-inputs-and-unresolvable-outputs-as-step-failures.md)
- [ADR 0082: A Run That Completes Has Succeeded](0082-a-run-that-completes-has-succeeded.md)
- [ADR 0083: Announce Steps and Stream JSON Lines Records](0083-announce-steps-and-stream-json-lines-records.md)
- [ADR 0084: Run Child Workflows as Separate Processes](0084-run-child-workflows-as-separate-processes.md)
- [ADR 0085: Report Judge Cost Beside Scorecards, Never in Them](0085-report-judge-cost-beside-scorecards-never-in-them.md)
- [ADR 0086: Add Benchmark Cases Only Deliberately, From Recorded Runs](0086-add-benchmark-cases-only-deliberately-from-recorded-runs.md)
- [ADR 0087: Bind Prompt Variables to Step Inputs by Name](0087-bind-prompt-variables-to-step-inputs-by-name.md)
- [ADR 0088: Parse Prompt Replies as JSON When Declared](0088-parse-prompt-replies-as-json-when-declared.md)
- [ADR 0089: Substitute Models in Context-Prompt Steps](0089-substitute-models-in-context-prompt-steps.md)
- [ADR 0090: Loop by Invoking Child Workflows from a Tool](0090-loop-by-invoking-child-workflows-from-a-tool.md)
- [ADR 0091: Evaluate the Final Generation's Proposals](0091-evaluate-the-final-generations-proposals.md)
- [ADR 0092: Promote an Optimization Experiment's Winner](0092-promote-an-optimization-experiments-winner.md)
- [ADR 0093: Budget Loops From Their Settings](0093-budget-loops-from-their-settings.md)
- [ADR 0094: Constant Step Inputs](0094-constant-step-inputs.md)
- [ADR 0095: Ship a Standard Tool Library](0095-ship-a-standard-tool-library.md)
- [ADR 0096: Accept Inputs as Values or References](0096-accept-inputs-as-values-or-references.md)
- [ADR 0097: Carry Invocations in a Versioned Job Envelope](0097-carry-invocations-in-a-versioned-job-envelope.md)
