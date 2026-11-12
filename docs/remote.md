# Sharing Workflows Through a Remote

A remote is an Azathoth instance other instances push workflows, tools and
benchmarks to, and pull them back from, with their lineage (ADR 0124). A
team keeps one remote; each person works on their own instance, pushes what
they made, and pulls what the others did.

A push sends each document's latest revision, the revisions it was reached
by, and what it needs there: the tool versions its tool steps use, the
child workflows its steps run, and the content its benchmark cases hold. It
sends only what the remote lacks. Production state, the model portfolio and
runs stay with each instance: a pulled workflow is promoted, and its models
authorized, where it is pulled.

This guide covers macOS and Windows. Each command is shown twice:

- for the macOS Terminal (zsh or bash);
- for Windows PowerShell 7.

On Linux, the macOS commands work unchanged.

## What You Need

- Azathoth installed in a venv, as in [Installing Azathoth](install.md), and
  that venv active.
- A clone of the repository, for the example workflow this guide pushes, as
  in [Getting Started](getting-started.md).
- Two terminals, both in the root of your clone, with the venv active in
  each: one serves the remote, the other is the instance that pushes and
  pulls.

This guide runs both on one machine, each with its own database. Across
machines the steps are the same, with the remote's URL in place of
`http://127.0.0.1:8470`, behind TLS, as in
[On Fargate](#on-fargate).

## 1. Install the Server

The server is an optional extra. Install it into the venv of the instance
that serves the remote:

```bash
python -m pip install "azathoth-ai[remote]"
```

```powershell
python -m pip install "azathoth-ai[remote]"
```

An instance that only pushes and pulls needs no extra.

## 2. Create the Remote and Its Token

In the first terminal, give the remote its own database, initialize it, and
create a token for the instance that will reach it:

```bash
export AZATHOTH_DATABASE=remote.db
azathoth init
azathoth remote token create laptop
```

```powershell
$env:AZATHOTH_DATABASE = "remote.db"
azathoth init
azathoth remote token create laptop
```

```text
Created remote token laptop.
Token: azr_<SECRET>
Keep the token now: this remote keeps only its digest, and cannot show it again.
```

Copy the token now. The remote keeps only its digest, so a token that is
lost is revoked and created again; see [Tokens](#tokens).

## 3. Serve It

In the same terminal:

```bash
azathoth remote serve
```

```powershell
azathoth remote serve
```

```text
Serving remote protocol 1 at http://127.0.0.1:8470; it refuses restricted data.
```

It listens on this machine only, on port 8470, until Ctrl-C stops it;
`--host` and `--port` choose others. In the second terminal, check that it
answers:

```bash
curl http://127.0.0.1:8470/health
```

```powershell
Invoke-RestMethod http://127.0.0.1:8470/health
```

It answers `{"status":"ok"}` to anyone. Everything else needs a token.

## 4. Push a Workflow

In the second terminal, make an instance holding the word-count example,
which needs no model, and give it the remote's token. The token is read
from `AZATHOTH_REMOTE_TOKEN`, so no command line holds it:

```bash
export AZATHOTH_DATABASE=laptop.db
azathoth init
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/word-count-messages.json
export AZATHOTH_REMOTE_TOKEN=<TOKEN>
```

```powershell
$env:AZATHOTH_DATABASE = "laptop.db"
azathoth init
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/word-count-messages.json
$env:AZATHOTH_REMOTE_TOKEN = "<TOKEN>"
```

Push the workflow:

```bash
azathoth remote push http://127.0.0.1:8470 --workflow a1000000-0000-4000-8000-000000000002
```

```powershell
azathoth remote push http://127.0.0.1:8470 --workflow a1000000-0000-4000-8000-000000000002
```

```text
Pushed to http://127.0.0.1:8470. Revisions received: 3. Revisions already held: 0. Content sent: 0.
Received tool 55555555-5555-5555-5555-555555555555@1.0.0 as revision 1.
Received tool 11111111-1111-1111-1111-111111111111@1.0.0 as revision 1.
Received workflow a1000000-0000-4000-8000-000000000002 as revision 1.
```

The two tools its steps use went first. Push again and nothing is sent,
since the remote holds it all:

```text
Pushed to http://127.0.0.1:8470. Revisions received: 0. Revisions already held: 3. Content sent: 0.
```

`--workflow`, `--tool <TOOL_ID>@<VERSION>` and `--benchmark` name what to
push, each given again for more. Each revision is numbered by the instance
that holds it; its digest, which `workflow show` names, is the same
everywhere.

## 5. Pull It Elsewhere

Make a third, empty instance and pull the workflow into it:

```bash
export AZATHOTH_DATABASE=desktop.db
azathoth init
azathoth remote pull http://127.0.0.1:8470 --workflow a1000000-0000-4000-8000-000000000002
```

```powershell
$env:AZATHOTH_DATABASE = "desktop.db"
azathoth init
azathoth remote pull http://127.0.0.1:8470 --workflow a1000000-0000-4000-8000-000000000002
```

```text
Pulled from http://127.0.0.1:8470. Revisions saved: 3. Revisions already held: 0. Content fetched: 0.
Saved tool 55555555-5555-5555-5555-555555555555@1.0.0 as revision 1.
Saved tool 11111111-1111-1111-1111-111111111111@1.0.0 as revision 1.
Saved workflow a1000000-0000-4000-8000-000000000002 as revision 1.
```

The pulled workflow is not in production here until it is promoted, and a
workflow with prompt steps runs only on models this instance authorizes.
The service API's `models.matching(requirements, scope="catalog")` names
the served models that meet a step's requirements, authorized here or not.

## 6. When Two People Change One Workflow

A remote moves only forward. If someone pushed a revision you do not hold,
your push of another is refused, and nothing of it is saved:

```text
Workflow <WORKFLOW_ID> has diverged: its latest revision here, <LATEST>, is not the one revision <DIGEST> builds on. Pull first, then push again.
```

Pull first. The remote's revisions are saved on the revision they build on,
which forks the workflow here, so neither your revision nor theirs is
lost:

```text
Forked <LINEAGE>: its pulled revisions build on an earlier revision here.
```

The pulled revision is now the latest. Keep it, or import yours again on
top of it, then push.

## 7. Restricted Data

A remote refuses restricted data unless it was started to hold it
(ADR 0123). A benchmark with a restricted case, and the content such a case
holds, is refused before anything is sent:

```text
This push carries restricted data, and this remote does not accept restricted data. Its operator accepts it by starting the remote with `azathoth remote serve --accept-restricted`.
```

Start a remote with `--accept-restricted` only where restricted data may be
kept, such as a database and network your organization has approved for
it:

```bash
azathoth remote serve --accept-restricted
```

```powershell
azathoth remote serve --accept-restricted
```

```text
Serving remote protocol 1 at http://127.0.0.1:8470; it accepts restricted data.
```

A pull leaves out restricted benchmarks unless it asks for them with
`--include-restricted`, and says which it withheld:

```text
Withheld <LINEAGE>: it is restricted; pull it with --include-restricted.
```

## 8. Before Shipping

A push warns, after its report and on standard error, of what would stop
its documents from running at the remote. A warning never refuses a push;
it says what to fix there:

```text
Warning: Tool <TOOL_ID>@<VERSION> needs <NAME>, which is not set at the remote; its steps fail there until it is.
Warning: Step <STEP_ID> of workflow <WORKFLOW_ID> runs workflow <CHILD_ID>, which is not in production at the remote; it cannot run there until the child is promoted.
Warning: Step <STEP_ID> of workflow <WORKFLOW_ID> uses model <MODEL>, which the remote has not authorized; it cannot run there until the remote's portfolio holds it.
```

A credential is checked by name only; the remote never says what any
variable holds. To see where everything stands before pushing, ask the
service API for a status, with `AZATHOTH_REMOTE_TOKEN` set as above:

```python
from azathoth import api

with api.open("laptop.db") as instance:
    status = instance.remote("http://127.0.0.1:8470").status()

    for component in status.components:
        print(component.lineage, component.relation)

    for model in status.models:
        print(model.identifier, model.authorized_locally, model.authorized_remotely)
```

Each component is `in_sync`, `ahead`, `behind`, `diverged`, `local_only`
or `remote_only`, and each model says whether it is authorized here and at
the remote. A status keeps the remote's portfolio each time it reaches it,
so when the remote cannot be reached, the status says so, its relations
are unknown, and its models are read from the portfolio last kept, as of
`portfolio_synced_at` (ADR 0125).

## Tokens

List a remote's tokens, and revoke one that is lost or no longer needed, on
the remote's own database:

```bash
azathoth remote token list
azathoth remote token revoke laptop
```

```powershell
azathoth remote token list
azathoth remote token revoke laptop
```

A revoked token no longer reaches the remote, and `remote token list --all`
still shows it, with when it was revoked. With the core's policy, every
token is its owner's: whoever holds one may do anything the owner may, so
give one to each machine, and revoke it when the machine goes. A policy
plugin, such as the team tier's, can decide more finely.

## In the Container

The container image includes the `remote` extra. With `IMAGE` named as in
[Running in a Container](container.md), serve its database volume as a
remote, listening on every interface inside the container and published to
this machine only:

```bash
docker run --rm -p 127.0.0.1:8470:8470 -v azathoth-data:/var/lib/azathoth $IMAGE remote serve --host 0.0.0.0
```

```powershell
docker run --rm -p 127.0.0.1:8470:8470 -v azathoth-data:/var/lib/azathoth $IMAGE remote serve --host 0.0.0.0
```

Create its tokens with the same image and volume:

```bash
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE remote token create laptop
```

```powershell
docker run --rm -v azathoth-data:/var/lib/azathoth $IMAGE remote token create laptop
```

## On Fargate

This deployment is described, not tested by Azathoth's own checks. The same
image serves a remote on Amazon ECS on Fargate:

- Run one task of a service with the command
  `remote serve --host 0.0.0.0`, its container port 8470.
- Put it behind an Application Load Balancer that ends TLS with your
  certificate, forwards to port 8470, and checks `/health`. The remote
  speaks plain HTTP, so never expose its port except through the load
  balancer.
- Keep its database in PostgreSQL, as in [Running on AWS](aws.md): set
  `AZATHOTH_DATABASE` to its URL from Secrets Manager, and run `init` once,
  as a one-off task, before the service starts, since a remote's tokens
  need schema version 5.
- Create tokens with one-off tasks running `remote token create <NAME>`,
  and read the token from the task's log, once.
- Add `--accept-restricted` to the command only where that database and its
  network are approved for restricted data.

## Troubleshooting

The remote has no token of that value; create one on the remote and set
`AZATHOTH_REMOTE_TOKEN` to it:

```text
This remote does not know the token given. Send one its owner created with `azathoth remote token create`, as `Authorization: Bearer <TOKEN>`.
```

No token is set in this terminal:

```text
No remote token was given; set AZATHOTH_REMOTE_TOKEN to one created on the remote with `azathoth remote token create`.
```

The remote is not running, or not at that URL:

```text
The remote at <URL> could not be reached: <REASON>
```

The two sides run versions of Azathoth that speak another protocol; upgrade
the older one:

```text
The remote speaks remote protocol <PROTOCOL>, and this Azathoth speaks remote protocol 1; run versions of Azathoth that speak the same protocol on both.
```

The serving instance lacks the `remote` extra:

```text
azathoth remote serve needs starlette and uvicorn, which are not installed; install azathoth-ai[remote].
```
