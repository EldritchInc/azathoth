# ADR 0053: Introduce the Azathoth Command-Line Application

- Status: Accepted
- Date: 2026-08-22

## Context

Azathoth's core library now provides durable configuration, runtime
reconstruction, executable workflow candidate generation, workflow execution,
empirical evaluation, experiments, and optimization.

Applications can reconstruct durable configuration and compose it with
process-local executable dependencies through `AzathothRuntime`.

Before this decision, however, operating Azathoth still required application
code.

```text
Python application
      │
      ├── reconstruct catalogs
      ├── configure providers
      ├── compose runtime
      └── invoke library APIs
```

OSS V1 requires a supported application-facing interface that can eventually
expose workflow execution, benchmarking, and optimization without requiring
users to write Python glue.

## Decision

Azathoth provides an installed command-line application.

```text
azathoth
```

The package declares a console-script entry point through project metadata.

```text
installed package
      │
      ▼
azathoth
      │
      ▼
azathoth.cli
```

The command-line application initially establishes:

- application startup;
- help output;
- package version output;
- standard argument errors;
- stable process exit behavior; and
- runtime bootstrap infrastructure.

Domain commands are deliberately introduced separately.

## Application Boundary

The command-line application is divided into two responsibilities.

```text
CLI shell
   │
   ├── argument parsing
   ├── help
   ├── version
   └── process behavior

CLI bootstrap
   │
   ├── configuration
   ├── durable reconstruction
   ├── provider attachment
   └── runtime composition
```

The shell does not eagerly bootstrap the runtime.

This keeps application metadata operations independent from storage and
provider configuration.

## Console Entry Point

The package exposes:

```text
azathoth
```

as an installed console command.

The command invokes the CLI application's `main()` function.

The application function returns an integer process status rather than
terminating the interpreter directly.

```text
main()
  │
  ▼
integer exit status
```

The installed console-script wrapper adapts that return value into the process
exit status.

The module entry point also supports:

```text
python -m azathoth.cli
```

and explicitly converts `main()` into `SystemExit`.

This keeps the application function directly testable while preserving normal
command-line process behavior.

## Initial CLI Behavior

The initial application supports:

```text
azathoth
azathoth --help
azathoth --version
```

Running `azathoth` without arguments displays help and exits successfully.

Help and version output are handled entirely by the command-line parser.

Invalid arguments use the parser's standard error behavior and nonzero exit
status.

## Version Authority

The CLI does not maintain an independent application version.

```text
azathoth.__version__
        │
        ▼
azathoth --version
```

The package version remains authoritative.

This prevents package metadata and CLI output from drifting independently.

## Runtime Configuration

CLI runtime bootstrap is configured through `CliRuntimeConfiguration`.

```text
CliRuntimeConfiguration
├── database
└── OpenRouter API key
```

The configuration may be constructed directly or derived from process
environment variables.

The initial environment variables are:

```text
AZATHOTH_DATABASE
OPENROUTER_API_KEY
```

When no database is configured, the CLI runtime configuration uses:

```text
azathoth.db
```

as the default application database path.

Provider credentials remain process-local configuration.

They are not persisted as model metadata.

## Credential Handling

The OpenRouter API key is represented as secret configuration.

It must not appear in normal configuration representations.

```text
environment
    │
    ▼
SecretStr
    │
    ▼
OpenRouterConfiguration
```

This preserves the existing provider boundary between durable model metadata
and runtime credentials.

## Runtime Bootstrap

`load_runtime()` reconstructs durable Azathoth configuration and composes it
into `AzathothRuntime`.

```text
SQLite database
      │
      ├── SQLiteWorkflowRepository
      │       │
      │       ▼
      │   WorkflowCatalogLoader
      │       │
      │       ▼
      │   WorkflowCatalog
      │
      ├── SQLiteModelRepository
      │       │
      │       ▼
      │   ModelCatalogLoader
      │       │
      │       ▼
      │   ModelCatalog
      │
      └── SQLiteToolRepository
              │
              ▼
          ToolCatalogLoader
              │
              ├── ToolCatalog
              └── ToolImplementationCatalog
```

Those reconstructed catalogs are then combined with process-local provider
implementations.

```text
reconstructed catalogs
        +
LanguageModelRegistry
        │
        ▼
AzathothRuntime
```

The CLI does not implement an alternative runtime composition path.

It consumes the runtime boundary already provided by the core library.

## One Application Database

The initial CLI bootstrap uses one configured SQLite database path for durable
workflow, model, and tool configuration.

```text
azathoth.db
├── workflow persistence
├── model persistence
└── tool persistence
```

Each subsystem retains its own repository abstraction and tables.

The CLI merely supplies the same configured database path to those existing
repositories.

This provides one application-level storage location without merging the
underlying persistence abstractions.

## Provider Runtime Loading

Durable model metadata and executable model implementations remain distinct.

```text
ModelCatalog
    │
    ├── known model A
    ├── known model B
    └── known model C
```

A model may be known without currently being executable.

When an OpenRouter API key is available:

```text
OpenRouterConfiguration
        +
ModelCatalog
        │
        ▼
OpenRouterModelRegistryLoader
        │
        ▼
LanguageModelRegistry
```

Only configured OpenRouter models are registered as executable OpenRouter
implementations.

The resulting provider registry is composed through the existing
provider-neutral `LanguageModelRegistry` composition boundary.

## Missing Provider Credentials

Missing OpenRouter credentials do not prevent durable configuration from being
reconstructed.

```text
ModelCatalog
    │
    ▼
known models

LanguageModelRegistry
    │
    ▼
no executable OpenRouter models
```

This distinction is intentional.

Commands that only inspect durable configuration should not require provider
credentials.

Future commands that require executable models may surface the existing
candidate-generation failure when the required runtime implementation is
unavailable.

## Lazy Runtime Bootstrap

The CLI shell does not load runtime state merely to start the application.

These operations:

```text
azathoth
azathoth --help
azathoth --version
```

do not:

- create the default database;
- open configured repositories;
- reconstruct catalogs;
- inspect provider credentials;
- construct provider implementations; or
- construct `AzathothRuntime`.

Instead:

```text
azathoth --help
      │
      ▼
argument parser
      │
      ▼
help
      │
      ▼
exit
```

Runtime bootstrap is reserved for domain commands that actually require
Azathoth state.

## Installed Application Contract

The CLI is tested through the actual console script installed beside the active
Python interpreter.

```text
Python environment
      │
      ├── python
      └── azathoth
              │
              ▼
          CLI application
```

The installed application contract verifies:

```text
azathoth
    → help
    → exit 0

azathoth --help
    → help
    → exit 0

azathoth --version
    → package version
    → exit 0

azathoth <invalid argument>
    → parser error
    → exit 2
```

It also verifies that help and version operations do not bootstrap runtime
configuration or create SQLite state.

## Relationship to Runtime Composition

The CLI sits above `AzathothRuntime`.

```text
CLI
 │
 ▼
runtime bootstrap
 │
 ▼
AzathothRuntime
```

It does not replace the runtime abstraction.

Future CLI commands should use the runtime rather than manually reconstructing
candidate-generation dependencies.

## Relationship to Domain Commands

This decision establishes the application shell and runtime bootstrap only.

It does not yet expose workflow, benchmark, experiment, or optimization
commands.

The intended progression is:

```text
CLI shell
    │
    ▼
runtime bootstrap
    │
    ▼
workflow commands
    │
    ▼
benchmark commands
    │
    ▼
optimization commands
```

Each command family can therefore be introduced against a stable application
boundary.

## Consequences

### Positive

- Azathoth is available as an installed terminal application.
- CLI behavior has a stable process-level contract.
- The package version remains the single version authority.
- Help and version operations require no runtime bootstrap.
- Runtime configuration has a dedicated application boundary.
- Provider credentials remain process-local.
- Durable configuration can be inspected without provider credentials.
- Existing repositories and catalog loaders remain authoritative.
- Existing `AzathothRuntime` composition remains authoritative.
- Future commands do not need to understand the complete dependency graph.
- The CLI introduces no additional framework dependency.

### Negative

- The initial application has no domain commands.
- SQLite is currently the CLI's application-level persistence configuration.
- OpenRouter is currently the only provider automatically attached by CLI
  bootstrap.
- Environment variables are currently the primary external runtime
  configuration source.
- Commands requiring runtime state must explicitly invoke bootstrap.

## Alternatives Considered

### Build Workflow Commands Before Establishing the Application Boundary

Rejected.

That would mix argument parsing, runtime construction, persistence, and domain
behavior in the first command implementation.

### Bootstrap Runtime During Every CLI Invocation

Rejected.

Help and version output should not depend on databases, credentials, provider
configuration, or runtime construction.

### Put Runtime Reconstruction Directly in Command Handlers

Rejected.

Command handlers should consume a supported bootstrap boundary rather than
reimplement repository and provider composition.

### Let AzathothRuntime Read Environment Variables

Rejected.

Environment configuration is an application concern.

`AzathothRuntime` remains independent from the CLI and from process environment
policy.

### Persist Provider Credentials

Rejected.

Credentials are process-local runtime configuration and remain outside durable
model metadata.

### Add a Third-Party CLI Framework

Rejected for OSS V1.

The standard-library argument parser provides the required application
semantics without adding another runtime dependency.

## Result

Azathoth now has a real application boundary.

```text
                     azathoth
                        │
             ┌──────────┴──────────┐
             │                     │
       shell operation        domain operation
             │                     │
      help / version           configuration
             │                     │
             ▼                     ▼
            exit                bootstrap
                                    │
                                    ▼
                             AzathothRuntime
```

The application exists.

The runtime can boot.

Domain commands can now be added without rebuilding either boundary.