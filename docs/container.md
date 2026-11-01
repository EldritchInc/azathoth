# Running Azathoth in a Container

Azathoth is also published as a container image (ADR 0101), at the same
version as the PyPI package:

```text
ghcr.io/eldritchinc/azathoth:1.1.0
```

The image holds Azathoth, its standard tools and OpenTelemetry tracing. It
is what Azathoth's cloud deployment runs, and it runs anywhere Docker does,
on Intel and ARM machines alike. You don't need Python on your machine to use
it.

This guide covers macOS and Windows. Each command is shown twice:

- for the macOS Terminal (zsh or bash);
- for Windows PowerShell 7.

On Linux, the macOS commands work unchanged. To install Azathoth with
Python instead, see [Installing Azathoth](install.md).

## What You Need

- [Docker Desktop](https://www.docker.com/products/docker-desktop/), running,
  or another Docker engine.
- On Windows, PowerShell 7 rather than Windows PowerShell 5.1, for the same
  reason as the install guide gives: 5.1 strips the inner quotes of the JSON
  passed to `--input`.

## 1. Pull the Image

Name the image once, so the commands below stay short:

```bash
IMAGE=ghcr.io/eldritchinc/azathoth:1.1.0
docker pull $IMAGE
docker run --rm $IMAGE --version
```

```powershell
$IMAGE = "ghcr.io/eldritchinc/azathoth:1.1.0"
docker pull $IMAGE
docker run --rm $IMAGE --version
```

`--version` prints `azathoth 1.1.0`. Everything after the image name is an
`azathoth` command, so `docker run --rm $IMAGE --help` lists them all, and
running the image with no command does the same.

Pin an exact version such as `1.1.0`. The tag `1.1` moves to each 1.1 patch
release, and `latest` to each release.

## 2. Give It a Database

A container keeps nothing once it is removed. Azathoth's database lives in
the folder `/var/lib/azathoth` inside the container, so mount a Docker volume
there, and every container you run shares it:

```bash
docker volume create azathoth-data
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE init
```

```powershell
docker volume create azathoth-data
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE init
```

```text
Database: /var/lib/azathoth/azathoth.db (created)
Installed tool run_workflow@1.0.0 revision 1.
Installed tool loop_workflow@1.1.0 revision 1.
```

The image never initializes a database by itself, so run `init` once per
volume. Running it again is safe, and after upgrading to a new image it
installs any new standard tools.

Prefer a named volume to a folder of your own. The container runs as its own
user, uid 10001, not as you; Docker gives a new named volume to that user,
but a folder you mount keeps its own owner, and on Linux the container can't
write to it until it belongs to uid 10001.

### Or a PostgreSQL database

Containers on several hosts can share one PostgreSQL database instead of a
volume. The image includes PostgreSQL support, so pass the database's URL as
`AZATHOTH_DATABASE` (see
[Optional: Sharing a Database With PostgreSQL](install.md#optional-sharing-a-database-with-postgresql)),
and run `init` once, from any one container:

```bash
docker run --rm -e AZATHOTH_DATABASE="postgresql://azathoth:<PASSWORD>@db.example.com:5432/azathoth" $IMAGE init
```

```powershell
docker run --rm -e AZATHOTH_DATABASE="postgresql://azathoth:<PASSWORD>@db.example.com:5432/azathoth" $IMAGE init
```

```text
Database: postgresql://azathoth@db.example.com:5432/azathoth (created)
Installed tool run_workflow@1.0.0 revision 1.
Installed tool loop_workflow@1.1.0 revision 1.
```

Then pass the same `-e AZATHOTH_DATABASE=…` wherever this guide passes
`-v azathoth-data:/var/lib/azathoth`. A server on your own machine is
`host.docker.internal` from inside a container, not `localhost`.

A password on the command line stays in your shell's history. To keep it
out, put the variables in a file that only you can read, one `NAME=value`
per line, and pass `--env-file` with its path instead of `-e`:

```bash
docker run --rm --env-file "$HOME/azathoth.env" $IMAGE workflow list
```

```powershell
docker run --rm --env-file "$HOME\azathoth.env" $IMAGE workflow list
```

## 3. Run the Examples

The examples aren't in the image. Clone the repository (see
[Get the Examples](install.md#6-get-the-examples)), and from inside it mount
its `examples` folder, read-only:

```bash
cd ~/azathoth-work/azathoth
docker run --rm -v azathoth-data:/var/lib/azathoth -v "$PWD/examples:/examples:ro" $IMAGE tool import /examples/tools/word-count.json
docker run --rm -v azathoth-data:/var/lib/azathoth -v "$PWD/examples:/examples:ro" $IMAGE tool import /examples/tools/word-count-process.json
docker run --rm -v azathoth-data:/var/lib/azathoth -v "$PWD/examples:/examples:ro" $IMAGE workflow import /examples/workflows/redundant-word-count.json
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result
```

```powershell
Set-Location ~/azathoth-work/azathoth
docker run --rm -v azathoth-data:/var/lib/azathoth -v "$($PWD.Path)\examples:/examples:ro" $IMAGE tool import /examples/tools/word-count.json
docker run --rm -v azathoth-data:/var/lib/azathoth -v "$($PWD.Path)\examples:/examples:ro" $IMAGE tool import /examples/tools/word-count-process.json
docker run --rm -v azathoth-data:/var/lib/azathoth -v "$($PWD.Path)\examples:/examples:ro" $IMAGE workflow import /examples/workflows/redundant-word-count.json
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result
```

It prints `8`, exactly as the installed command does. Paths you pass to
Azathoth are paths inside the container, such as `/examples/...`, not paths
on your machine.

Child workflows run inside the container too, because the standard tools
start the container's own Azathoth. The child-workflow example from the
[Examples Tour](examples.md) works unchanged once its documents are imported.

## 4. Pass Your Keys

A provider key is passed to each container that needs it, never built into
an image. `-e NAME` with no value copies the variable from your terminal, so
the key never appears in the command:

```bash
export OPENROUTER_API_KEY="sk-or-..."
docker run --rm -e OPENROUTER_API_KEY -v azathoth-data:/var/lib/azathoth $IMAGE model list
```

```powershell
$env:OPENROUTER_API_KEY = "sk-or-..."
docker run --rm -e OPENROUTER_API_KEY -v azathoth-data:/var/lib/azathoth $IMAGE model list
```

[Connecting OpenRouter](openrouter.md) covers getting a key and authorizing
models; add `-e OPENROUTER_API_KEY` to each of its commands.

## 5. Run Jobs

`job run` reads a job request on standard input when its source is `-`, so a
program can drive Azathoth in a container with nothing but pipes. Pass `-i`
to keep standard input open:

```bash
docker run --rm -i -e OPENROUTER_API_KEY -v azathoth-data:/var/lib/azathoth $IMAGE job run - < request.json
```

```powershell
Get-Content -Raw request.json | docker run --rm -i -e OPENROUTER_API_KEY -v azathoth-data:/var/lib/azathoth $IMAGE job run -
```

Standard output carries exactly one job result, and nothing else. The
[CLI Reference](../src/azathoth/cli/README.md#run-a-job) describes requests
and results.

## 6. Harden It

The image runs as a non-root user, and works with a read-only root
filesystem. Only two places must be writable: the database's folder, and
`/tmp`, where process tools write the scripts they run:

```bash
docker run --rm --read-only --tmpfs /tmp -v azathoth-data:/var/lib/azathoth $IMAGE workflow list
```

```powershell
docker run --rm --read-only --tmpfs /tmp -v azathoth-data:/var/lib/azathoth $IMAGE workflow list
```

The image runs `tini` as its first process, so stopping a container stops
its workflow and every tool process it started.

## 7. Trace It

The image includes OpenTelemetry. Turn it on as the install guide describes
(see [Optional: Tracing With OpenTelemetry](install.md#optional-tracing-with-opentelemetry)),
passing the variables to the container. A collector on your own machine is
`host.docker.internal` from inside a container:

```bash
docker run --rm -e AZATHOTH_OTEL=1 -e OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318 -v azathoth-data:/var/lib/azathoth $IMAGE workflow run a1000000-0000-4000-8000-000000000001 --input '"the old ones wait"' --output result
```

```powershell
docker run --rm -e AZATHOTH_OTEL=1 -e OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318 -v azathoth-data:/var/lib/azathoth $IMAGE workflow run a1000000-0000-4000-8000-000000000001 --input '"the old ones wait"' --output result
```

## Building the Image Yourself

From a clone of the repository, `docker build` builds the image from the
checkout, with nothing else prepared:

```bash
docker build --tag azathoth .
docker run --rm azathoth --version
```

```powershell
docker build --tag azathoth .
docker run --rm azathoth --version
```

[Contributing](../CONTRIBUTING.md#container-tests) covers testing it.

## Upgrading and Cleaning Up

To upgrade, pull the new version, then run `init` on your volume once, so it
gets any new standard tools:

```bash
IMAGE=ghcr.io/eldritchinc/azathoth:<VERSION>
docker pull $IMAGE
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE init
```

```powershell
$IMAGE = "ghcr.io/eldritchinc/azathoth:<VERSION>"
docker pull $IMAGE
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE init
```

To remove everything, including the database, delete the volume and the
image:

```bash
docker volume rm azathoth-data
docker image rm $IMAGE
```

```powershell
docker volume rm azathoth-data
docker image rm $IMAGE
```

## Troubleshooting

**An error ending in `unable to open database file`**: the database's folder
isn't writable by the container's user. Use a named volume (step 2), or, on Linux, make the
folder you mount belong to uid 10001.

**`Connection refused`** from `init` with a PostgreSQL URL naming
`localhost`: inside a container, `localhost` is the container itself. Name
the server's host, or `host.docker.internal` for a server on your own
machine.

**A document you import can't be found**: its path is outside the
container. Mount the folder that holds it, and pass the path
inside the container (step 3).

**A job is rejected as `invalid_request`** although the request is fine:
`docker run` was given `job run -` without `-i`, so the container read an
empty standard input (step 5).

**`Value must be valid JSON`** for an `--input` value on Windows: you are in
Windows PowerShell 5.1. Use PowerShell 7.
