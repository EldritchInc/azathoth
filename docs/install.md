# Installing Azathoth

Azathoth is published on PyPI as `azathoth-ai`. Installing it gives you the
`azathoth` command.

With Azathoth, you build a workflow by composing JSON documents: steps,
prompts, models, tools and child workflows. You write code only for tools.
So you don't need to be a Python developer to use it. You do need a working
Python, because that is what Azathoth runs on.

This guide covers macOS and Windows. Each command is shown twice:

- for the macOS Terminal (zsh or bash);
- for Windows PowerShell.

On Linux, the macOS commands work unchanged.

To work on Azathoth itself rather than use it, see
[Contributing](../CONTRIBUTING.md) instead. To run Azathoth in a container,
without installing Python, see [Running in a Container](container.md).

## What You Need

- Python 3.11 or newer.
- A terminal: Terminal on macOS, or PowerShell 7 on Windows.
- About five minutes.

You don't need an OpenRouter key to install Azathoth, or to import and
inspect workflows. You need one only to run steps that call language models.
[Connecting OpenRouter](openrouter.md) covers getting one.

## 1. Install Python

Check what you already have:

```bash
python3 --version
```

```powershell
py --version
```

If the version is 3.11 or newer, skip to step 2.

### macOS

The `python3` that comes with Apple's Command Line Tools is too old for
Azathoth. Install a current Python in one of two ways:

- the macOS installer from [python.org](https://www.python.org/downloads/);
- or [Homebrew](https://brew.sh).

With Homebrew:

```bash
brew install python@3.13
python3.13 --version
```

After installing from python.org, open a new Terminal window and use
`python3.13` (or whichever version you installed) in the next step.

### Windows

Install Python from [python.org](https://www.python.org/downloads/). On the
installer's first screen, select **Add python.exe to PATH**. Alternatively,
use `winget`:

```powershell
winget install Python.Python.3.13
py -3.13 --version
```

Open a new PowerShell window after installing.

Use PowerShell 7 rather than the Windows PowerShell 5.1 that comes with
Windows. Azathoth takes JSON on the command line, as in
`--input '"hello"'`, and Windows PowerShell 5.1 strips the inner double
quotes before Azathoth sees them. PowerShell 7 passes them through intact.
Install it, then open **PowerShell 7** from the Start menu and check the
version:

```powershell
winget install --id Microsoft.PowerShell --source winget
$PSVersionTable.PSVersion
```

The version should start with 7. Use PowerShell 7 for every command in these
guides.

If typing `python` opens the Microsoft Store, turn the Store's aliases off:
Settings → Apps → Advanced app settings → App execution aliases. Then switch
off **python.exe** and **python3.exe**.

## 2. Create a Virtual Environment

A virtual environment ("venv") is a private copy of Python for one project.
Azathoth must be installed in an activated venv.

### Why not pipx or `uv tool`?

Some of Azathoth's own tools start Python as a child process:

- `run_workflow`, which calls a child workflow;
- `loop_workflow`, which repeats a child workflow;
- `validate_workflow`, which checks a workflow document.

They run whichever `python` comes first on your `PATH`, and that Python must
be able to import Azathoth. An activated venv puts its own `python` first.

`pipx` and `uv tool install` work differently. They hide Azathoth in an
environment of its own and expose only the `azathoth` command. The `python`
on your `PATH` is then a different Python that can't see Azathoth. Ordinary
workflows still run, but any workflow that uses those tools fails with
`No module named azathoth`.

### Create and activate it

Make a folder for your Azathoth work, then create the venv inside it:

```bash
mkdir -p ~/azathoth-work
cd ~/azathoth-work
python3.13 -m venv .venv
source .venv/bin/activate
```

```powershell
New-Item -ItemType Directory -Force -Path ~/azathoth-work | Out-Null
Set-Location ~/azathoth-work
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
```

Use the Python version you installed in step 1, such as `python3.12` or
`py -3.12`.

Once the venv is active, your prompt starts with `(.venv)`, and both `python`
and `pip` refer to the venv. You don't need `python3` or `py` again until you
create another venv.

### Windows: allowing the activation script

If PowerShell refuses with "running scripts is disabled on this system",
allow local scripts for your user account once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1
```

### Windows: UTF-8 output

Workflows produce text in any language, and Azathoth writes it as UTF-8.
Windows terminals don't default to UTF-8. Without these two settings, saving
a result with `>` can garble any character outside plain English, such as an
accented letter, a curly quote or a dash:

```powershell
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

They last only for this window. To apply them in every new PowerShell window,
add them to your PowerShell profile once:

```powershell
if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force | Out-Null }
Add-Content -Path $PROFILE -Value '$env:PYTHONUTF8 = "1"', '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()'
```

macOS terminals already use UTF-8.

## 3. Install Azathoth

With the venv active:

```bash
python -m pip install --upgrade pip
python -m pip install azathoth-ai
```

```powershell
python -m pip install --upgrade pip
python -m pip install azathoth-ai
```

## 4. Check the Installation

First, confirm that the command runs:

```bash
azathoth --version
azathoth --help
```

```powershell
azathoth --version
azathoth --help
```

`azathoth --version` prints the installed version, for example
`azathoth 1.0.0`.

Then confirm that the `python` on your `PATH` is the venv's, and that it can
import Azathoth. Azathoth's child-process tools depend on this:

```bash
command -v python
python -c "import azathoth; print(azathoth.__version__)"
```

```powershell
(Get-Command python).Source
python -c "import azathoth; print(azathoth.__version__)"
```

The first line should print a path inside your folder that ends in
`.venv/bin/python` (macOS) or `.venv\Scripts\python.exe` (Windows). The second
should print the same version as `azathoth --version`.

## 5. Choose a Database

Azathoth keeps everything it knows in one SQLite file:

- imported workflows, tools, goals and benchmarks;
- authorized models;
- runs, experiments, promotions and invocations.

By default the file is `azathoth.db` in whatever folder you are in when you
run a command. Set `AZATHOTH_DATABASE` so that every command uses the same
file wherever you run it:

```bash
export AZATHOTH_DATABASE="$HOME/azathoth-work/azathoth.db"
```

```powershell
$env:AZATHOTH_DATABASE = "$HOME\azathoth-work\azathoth.db"
```

Then create the database and install Azathoth's standard tools into it:

```bash
azathoth init
```

```powershell
azathoth init
```

```text
Database: /Users/you/azathoth-work/azathoth.db (created)
Installed tool run_workflow@1.0.0 revision 1.
Installed tool loop_workflow@1.1.0 revision 1.
```

The standard tools ship inside the package, so composing workflows needs no
copy of the repository:

- `run_workflow` runs a child workflow once;
- `loop_workflow` runs a child workflow repeatedly.

Like every tool, they reach the database only by a recorded import, which is
what `init` does. It needs no provider key, and running it again is safe: it
reports each tool as already installed and writes nothing. It stops at the
database and its tools. Authorizing models needs a provider key, so it is a
separate step (see [Connecting OpenRouter](openrouter.md)).

To start over, delete the file and run `azathoth init` again.

To share one database between several machines, see
[Optional: Sharing a Database With PostgreSQL](#optional-sharing-a-database-with-postgresql).

## 6. Get the Examples

The standard tools are part of the PyPI package, but the examples aren't.
They live in the repository. Clone it next to your venv:

```bash
cd ~/azathoth-work
git clone https://github.com/EldritchInc/azathoth.git
```

```powershell
Set-Location ~/azathoth-work
git clone https://github.com/EldritchInc/azathoth.git
```

If you don't have `git`, download the repository as a ZIP from
[GitHub](https://github.com/EldritchInc/azathoth) (**Code** → **Download
ZIP**) and unzip it into `azathoth-work`.

The example commands assume you run them from inside the repository folder:

```bash
cd ~/azathoth-work/azathoth
```

```powershell
Set-Location ~/azathoth-work/azathoth
```

## Optional: Sharing a Database With PostgreSQL

The SQLite file of step 5 suits one machine. When Azathoth runs on several
machines, or in several containers, that must share what they know, keep it
in a PostgreSQL database instead. Most people don't need this; skip it unless
you do.

You need a PostgreSQL server, version 15 or later, and an empty database on
it that you may create tables in. PostgreSQL support is an optional extra.
Install it into the same venv:

```bash
python -m pip install "azathoth-ai[postgres]"
```

```powershell
python -m pip install "azathoth-ai[postgres]"
```

Then set `AZATHOTH_DATABASE` to the database's URL instead of a file:

```bash
export AZATHOTH_DATABASE="postgresql://azathoth:<PASSWORD>@db.example.com:5432/azathoth"
```

```powershell
$env:AZATHOTH_DATABASE = "postgresql://azathoth:<PASSWORD>@db.example.com:5432/azathoth"
```

The URL is PostgreSQL's own, so anything it accepts works, such as
`?sslmode=require` at the end. To keep the password out of the URL, leave it
out and set `PGPASSWORD`, or use a `.pgpass` file, as you would for `psql`.

Create the schema once, from any one machine:

```bash
azathoth init
```

```powershell
azathoth init
```

```text
Database: postgresql://azathoth@db.example.com:5432/azathoth (created)
Installed tool run_workflow@1.0.0 revision 1.
Installed tool loop_workflow@1.1.0 revision 1.
```

Azathoth never shows the password: every message names the database without
it. Unlike an SQLite file, a PostgreSQL database must be initialized before
anything else can use it; until it is, every command stops with:

```text
Database postgresql://azathoth@db.example.com:5432/azathoth is not initialized; run azathoth init.
```

Running `init` again is safe, from any number of machines at once. A database
already in use by SQLite stays where it is: Azathoth does not copy one into
the other.

## Optional: Tracing With OpenTelemetry

Azathoth can send a trace of every workflow it runs to the tracing backend
you already use, such as a local OpenTelemetry Collector, Honeycomb, Datadog
or AWS X-Ray. Most people don't need this; skip it unless you operate
Azathoth alongside other services.

Tracing is an optional extra. Install it into the same venv:

```bash
python -m pip install "azathoth-ai[otel]"
```

```powershell
python -m pip install "azathoth-ai[otel]"
```

Then turn it on, and tell it where to send spans. Everything except
`AZATHOTH_OTEL` is OpenTelemetry's own standard configuration:

```bash
export AZATHOTH_OTEL=1
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
export OTEL_SERVICE_NAME="azathoth"
```

```powershell
$env:AZATHOTH_OTEL = "1"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
$env:OTEL_SERVICE_NAME = "azathoth"
```

Spans go out over OTLP with HTTP and protobuf; gRPC isn't supported. A
backend that needs an API key takes it in `OTEL_EXPORTER_OTLP_HEADERS`, for
example `x-honeycomb-team=<KEY>`. The service name defaults to `azathoth`.

To check that tracing works without a backend, print the spans instead. They
go to stderr, so a command's own output is unchanged:

```bash
export OTEL_TRACES_EXPORTER=console
```

```powershell
$env:OTEL_TRACES_EXPORTER = "console"
```

`azathoth workflow run`, `azathoth workflow invoke` and `azathoth job run`
are traced. Each workflow run is one trace, with a span for each step, its
model, tokens, cost, retries and confidence. A child workflow continues its
parent's trace, under the step that started it. Spans never carry what a
workflow read, wrote or said: no inputs, prompts, replies, outputs or error
messages. Those stay in Azathoth's database, and each span names the run or
invocation to look up with `azathoth run show` or `azathoth invocation show`.

Child workflows need the 1.1 standard tools to pass the tracing settings on.
If you initialized your database before 1.1, run `azathoth init` again.

If `AZATHOTH_OTEL` is set but the extra isn't installed, a traced command
runs nothing and says so:

```text
AZATHOTH_OTEL is set, but OpenTelemetry is not installed; install azathoth-ai[otel].
```

To turn tracing off, unset `AZATHOTH_OTEL`:

```bash
unset AZATHOTH_OTEL
```

```powershell
Remove-Item Env:AZATHOTH_OTEL
```

The [telemetry reference](../src/azathoth/telemetry/README.md) lists every
span and attribute.

## Each New Terminal

A venv and an environment variable last only as long as the terminal window.
In each new window, run:

```bash
cd ~/azathoth-work
source .venv/bin/activate
export AZATHOTH_DATABASE="$HOME/azathoth-work/azathoth.db"
```

```powershell
Set-Location ~/azathoth-work
.venv\Scripts\Activate.ps1
$env:AZATHOTH_DATABASE = "$HOME\azathoth-work\azathoth.db"
```

On Windows, also apply the UTF-8 settings, unless your PowerShell profile
already does (see
[Windows: UTF-8 output](#windows-utf-8-output)).

If you trace, set `AZATHOTH_OTEL` and the `OTEL_*` variables again too (see
[Optional: Tracing With OpenTelemetry](#optional-tracing-with-opentelemetry)).

## Upgrading, Leaving and Uninstalling

Upgrade to the latest release, then install any new versions of the
standard tools into your database:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

A release that changes a standard tool ships it as a new version, which is
added beside the old one. Your workflows keep the exact tool versions they
name, so upgrading never changes what an existing workflow runs.

Upgrading to 1.1 is the one exception. Process tools stop inheriting your
environment, so a tool sees your provider key or database only if it grants
itself them. The 1.1 standard tools do, as new revisions of the same
versions, and `azathoth init` installs them; until it runs, child workflows
fail. A process tool of your own that relied on an inherited variable must
grant it; see
[Process Environment](../src/azathoth/tools/README.md#process-environment).

To leave the venv without closing the terminal, run `deactivate`.

To uninstall, deactivate and then delete the venv folder. Your database
is a separate file and stays where it is.

```bash
deactivate
rm -rf ~/azathoth-work/.venv
```

```powershell
deactivate
Remove-Item -Recurse -Force ~/azathoth-work/.venv
```

## Troubleshooting

**`azathoth: command not found`**, or **`The term 'azathoth' is not
recognized`**: the venv isn't active in this terminal. Activate it again (see
[Each New Terminal](#each-new-terminal)).

**`No module named azathoth`** from a child or loop workflow: the `python` on
your `PATH` isn't the venv's. This usually means Azathoth was installed with
`pipx` or `uv tool`, or the `azathoth` command was run by its full path without
the venv being activated. Activate the venv and check step 4 again.

**`requires a different Python`** from `pip`: the venv was made with a Python
older than 3.11. Delete `.venv`, then create it again (step 2) with a newer
Python.

**`Value must be valid JSON`** for an `--input` value on Windows: you are in Windows
PowerShell 5.1, which strips the inner quotes. Use PowerShell 7 (step 1).

**Garbled characters in a saved result on Windows**, such as `â€"` where a
dash should be: apply the UTF-8 settings (see
[Windows: UTF-8 output](#windows-utf-8-output)), then run the command again.

**`psycopg is not installed`**: `AZATHOTH_DATABASE` is a PostgreSQL URL, but
the `postgres` extra isn't installed in this venv (see
[Optional: Sharing a Database With PostgreSQL](#optional-sharing-a-database-with-postgresql)).

**`is not initialized; run azathoth init`**: the PostgreSQL database has no
Azathoth schema yet. Run `azathoth init` once.

**PowerShell won't run `Activate.ps1`**: set the execution policy (see
[Windows: allowing the activation script](#windows-allowing-the-activation-script)).

## Next

- [Connecting OpenRouter](openrouter.md): a key, models and judges.
- [Examples Tour](examples.md): every example, in order.
