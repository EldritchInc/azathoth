# Command-Line Interface

`azathoth.cli` provides the installed Azathoth command-line application and its
runtime bootstrap boundary.

## Installation Entry Point

Installing Azathoth exposes:

```text
azathoth
```

as a console command.

The package also supports:

```text
python -m azathoth.cli
```

The installed console entry point is declared through project metadata and
invokes the CLI application's `main()` function.

## Application Shell

The initial CLI supports:

```bash
azathoth
azathoth --help
azathoth --version
```

Running without arguments displays help.

The package version is the authoritative CLI version.

```text
azathoth.__version__
        │
        ▼
azathoth --version
```

Invalid arguments use standard parser error behavior.

## Application Structure

The CLI deliberately separates shell behavior from runtime bootstrap.

```text
azathoth.cli
├── application
│   ├── parser
│   ├── help
│   ├── version
│   └── process status
│
├── configuration
│   └── runtime configuration
│
└── bootstrap
    └── AzathothRuntime construction
```

Help and version operations do not require runtime configuration.

## Runtime Configuration

`CliRuntimeConfiguration` describes the application configuration required to
bootstrap an Azathoth runtime.

```text
CliRuntimeConfiguration
├── database
└── openrouter_api_key
```

Configuration may be created directly:

```python
configuration = CliRuntimeConfiguration(
    database=database,
)
```

or loaded from the environment:

```python
configuration = CliRuntimeConfiguration.from_environment()
```

## Environment Variables

The initial CLI runtime recognizes:

```text
AZATHOTH_DATABASE
OPENROUTER_API_KEY
```

`AZATHOTH_DATABASE` selects the SQLite database containing durable application
configuration.

When absent or empty, the default is:

```text
azathoth.db
```

`OPENROUTER_API_KEY` supplies process-local credentials for executable
OpenRouter model implementations.

An absent or empty key leaves OpenRouter models known but non-executable.

## Runtime Bootstrap

`load_runtime()` reconstructs durable application state and composes the
process-local runtime.

```python
configuration = CliRuntimeConfiguration.from_environment()

runtime = load_runtime(configuration)
```

The bootstrap path is:

```text
configured SQLite database
        │
        ├── workflows
        ├── models
        └── tools
        │
        ▼
existing repositories
        │
        ▼
existing catalog loaders
        │
        ▼
reconstructed catalogs
        │
        +
provider runtime implementations
        │
        ▼
AzathothRuntime
```

The CLI does not implement alternative repository, catalog, provider, or
runtime abstractions.

## One SQLite Application Database

The CLI supplies the same configured SQLite path to the existing workflow,
model, and tool repositories.

```text
azathoth.db
├── workflow tables
├── model tables
└── tool tables
```

The persistence subsystems remain independent.

The shared path is an application configuration decision rather than a merged
repository abstraction.

## OpenRouter Bootstrap

When OpenRouter credentials are configured:

```text
ModelCatalog
        +
OpenRouterConfiguration
        │
        ▼
OpenRouterModelRegistryLoader
        │
        ▼
LanguageModelRegistry
```

Only OpenRouter models present in the reconstructed model catalog are attached
as executable implementations.

The registry is then supplied to `AzathothRuntime`.

No provider API request is required merely to construct the runtime registry.

## Known Versus Executable Models

The CLI preserves the distinction between durable model metadata and executable
runtime implementations.

Without credentials:

```text
ModelCatalog
├── openrouter/model-a
└── openrouter/model-b

LanguageModelRegistry
└── empty
```

With credentials:

```text
ModelCatalog
├── openrouter/model-a
└── openrouter/model-b

LanguageModelRegistry
├── openrouter/model-a
└── openrouter/model-b
```

This allows future inspection commands to operate without requiring provider
credentials.

## Lazy Bootstrap

The application shell does not automatically invoke `load_runtime()`.

```text
azathoth --help
      │
      ▼
parser
      │
      ▼
exit
```

not:

```text
azathoth --help
      │
      ▼
database
      │
      ▼
providers
      │
      ▼
runtime
      │
      ▼
help
```

Runtime bootstrap should occur only when a domain command needs Azathoth state.

## Process Contract

The installed console application is tested as a real subprocess.

The supported shell behavior is:

```text
command                       result
────────────────────────────────────────────
azathoth                      help, exit 0
azathoth --help               help, exit 0
azathoth --version            version, exit 0
azathoth <invalid argument>   error, exit 2
```

Help and version operations must not create the default database or otherwise
bootstrap runtime state.

## Current Scope

The CLI foundation deliberately does not yet expose domain commands.

Not yet included:

```text
workflow list
workflow show
workflow run
benchmark commands
experiment commands
optimization commands
```

Those commands build on the shell and bootstrap boundaries established here.