# ADR 0101: Ship Azathoth as a Container Image

- Status: Accepted
- Date: 2026-11-01
- Decided in: #118

## Context

Azathoth 1.1 runs on AWS: behind a queue, invoked by programs through the job
envelope (ADR 0097), traced into the operator's backend (ADR 0100). Every
piece that follows, the Postgres repositories, Bedrock, the queue worker and
the deploy stack, runs in a container, and they all need the same one.

Today Azathoth ships only as a wheel on PyPI. Turning that into a working
container is not just `pip install`. Three things in Azathoth make it easy to
get wrong:

- The standard composition tools run `python -m azathoth.cli` as a child
  process (ADR 0084, ADR 0090), using whichever `python` is first on `PATH`.
  That Python must be the one Azathoth is installed in, which is why the
  install guide rules out `pipx` and `uv tool`.
- Process tools spawn processes of their own, so whatever runs as PID 1 must
  reap them and forward signals.
- Process tools write their source to a temporary script before running it,
  so a container whose root filesystem is read-only needs a writable
  temporary directory.

An image that gets one of these wrong still starts, prints its help and runs
simple workflows. It only fails when a workflow composes a child, or when it
is stopped.

## Decision

### One image

Azathoth is published as one image, at the same version as the wheel:

```text
ghcr.io/eldritchinc/azathoth:1.1.0
```

It holds Azathoth, its standard tool library, and the `otel` extra. Tracing
stays off until `AZATHOTH_OTEL` is set (ADR 0100), so including the extra
costs only size. A later extra that 1.1 needs in the cloud, such as the
Postgres or Bedrock support, is added to the image by the decision that adds
it.

The image holds no examples and no copy of the repository. Workflow, tool
and job documents are mounted or piped in.

### The image

The image is built from the repository by a multi-stage `Dockerfile`:

- The builder stage builds the wheel from the checkout, so `docker build .`
  needs nothing prepared.
- The runtime stage starts from `python:3.13-slim-trixie`: Debian 13, and the
  newest Python that CI tests. It keeps `bash`, which a process tool may
  declare as its command.
- Azathoth is installed from that wheel into a virtual environment at
  `/opt/azathoth/venv`, whose `bin` comes first on `PATH`. So `python` in the
  container is Azathoth's Python, and child workflows run.

At run time:

| Setting | Value |
| --- | --- |
| Entrypoint | `tini -- azathoth` |
| Default command | `--help` |
| User | `azathoth`, uid and gid 10001 |
| Working directory | `/var/lib/azathoth` |
| `AZATHOTH_DATABASE` | `/var/lib/azathoth/azathoth.db` |
| Python | `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1` |
| Locale | `LANG=C.UTF-8` |

So the container's arguments are an `azathoth` command:

```bash
docker run --rm ghcr.io/eldritchinc/azathoth:1.1.0 --version
docker run --rm -i ghcr.io/eldritchinc/azathoth:1.1.0 job run - < request.json
```

`tini` is PID 1. It reaps the processes that tools leave behind and forwards
signals, so stopping a container stops its workflow, whether or not the
platform runs an init of its own.

Output is unbuffered, so `--output jsonl` streams step records as they
happen, and every stream is UTF-8.

### Data

The image declares no volume. `/var/lib/azathoth` holds the SQLite database
by default, and a deployment mounts it, or points `AZATHOTH_DATABASE`
somewhere it mounts. An unmounted container keeps its database only as long
as the container exists.

The image never initializes a database by itself. A container whose every
start writes to its database would be surprising, and would race when
several start at once. A deployment runs `init` once, as it would on a
laptop:

```bash
docker run --rm -v azathoth-data:/var/lib/azathoth ghcr.io/eldritchinc/azathoth:1.1.0 init
```

Provider keys and tracing configuration are passed as environment variables
at run time. Nothing secret is baked into the image.

### Read-only root

The image runs with a read-only root filesystem. Only two places must be
writable: the database's folder, and the temporary directory, where process
tools write their scripts:

```bash
docker run --rm --read-only --tmpfs /tmp -v azathoth-data:/var/lib/azathoth \
    ghcr.io/eldritchinc/azathoth:1.1.0 workflow list
```

### Architectures and tags

Images are built for `linux/amd64` and `linux/arm64`, so they run on Graviton
as well as on x86. A release tag `vX.Y.Z` publishes:

| Tag | Moves |
| --- | --- |
| `X.Y.Z` | Never |
| `X.Y` | To each patch release of `X.Y` |
| `latest` | To each release |

A deployment pins `X.Y.Z`.

### Publishing

The release workflow publishes the image to the GitHub Container Registry,
public, from the commit it tags, after the wheel is built. Before pushing,
it runs the image and requires `azathoth --version` to print the tag's
version. It pushes with the workflow's own token, so no credential is stored.
A manual run of the release workflow builds both architectures and pushes
nothing, just as it publishes the wheel only to TestPyPI.

### Verified on every change

CI builds the image on every pull request and runs it: its version, its
user, `init`, the child-workflow example end to end, `job run` over
standard input, a read-only root, and tracing to the console without
touching stdout. These tests need Docker, so they run only when
`AZATHOTH_RUN_CONTAINER_TESTS=1` is set, as the live OpenRouter tests run
only with their own flag. The test matrix and `make check` stay free of
Docker.

### Not decided here

- Mirroring the image to ECR, and how a deployment pulls it (ADR 0109).
- Pinning the base image by digest, attestations and signing (ADR 0109).
- A health check. The image runs commands; the queue worker (ADR 0107)
  decides its own.

## Consequences

### Positive

- Every 1.1 component runs the same image, built from the commit its
  version names.
- Child workflows, tracing and the standard tools work in the container as
  on a laptop, and CI proves it on every change.
- The image runs as non-root on a read-only root filesystem, on amd64 and
  arm64.
- No secret or database is ever baked into the image.

### Negative

- The image is several times the size of the wheel, mostly Python itself.
- The base image is pinned by tag, so a rebuilt release may contain a newer
  Debian or Python patch than the first build did.
- A deployment must run `init` once, and mount its data.
- CI gains a job that takes minutes, and the arm64 image is built under
  emulation.

## Alternatives Considered

### Install with `pipx` or into the system Python

Rejected. `pipx` hides Azathoth from the `python` on `PATH`, so child
workflows fail. Installing into the image's system Python works, but mixes
Azathoth with whatever Debian or the base image installs, and a later layer
can break it.

### Alpine

Rejected. Its musl libc makes some dependencies build from source, which is
slow and fragile, and saves little once Python is included.

### Distroless

Rejected. It has no shell, so a process tool that declares `bash` as its
command fails, and it is harder to debug.

### Install the published wheel instead of building one

Rejected. Building from the checkout lets anyone run `docker build .`, and
the release checks the image's version against its tag anyway.

### Initialize the database on start

Rejected. It writes to the database on every start, races between
containers, and hides a step a deployment should run deliberately.

### Docker Hub or ECR

Rejected for publishing. GitHub's registry needs no stored credential in the
release workflow, and sits beside the repository. A deployment that needs
ECR mirrors the image there (ADR 0109).
