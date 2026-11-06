
Azathoth 1.2 serves workflows to AI clients. `azathoth-mcp`, a new package
released with Azathoth at the same version, offers the promoted workflows an
operator lists as Model Context Protocol tools, to Claude Desktop, IDEs and
agents, locally over stdio or to a team over HTTP behind the organization's
identity provider. Everything 1.1 promised is unchanged: documents, commands,
documented output and the database schema are as they were.

The AWS stack, the worker and the S3 tools are unchanged, and the image only
gained `azathoth-mcp`, which the stack does not run, so this release was not
deployed to the AWS sandbox again
([Release Validation](https://github.com/EldritchInc/azathoth/blob/main/docs/release-validation.md#9-the-aws-deployment)).

### Serving Workflows to AI Clients

- **`azathoth-mcp` serves promoted workflows as MCP tools.** It is a separate
  distribution, released with Azathoth at the same version and requiring its
  minor release. Only the workflows an operator lists in an exposure document
  are offered, each as one tool, under the name and description written for
  it; nothing that changes a workflow is ever offered ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **Every call is a recorded, idempotent invocation** of the workflow's
  active production revision, run as `job run` runs a job request: a repeated
  key replays, an interrupted invocation resumes, and the caller is recorded
  with it. `get_invocation` returns an invocation's input, outcome, caller and
  run, step by step ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **Over HTTP it is an OAuth 2.1 resource server.** It accepts only signed
  tokens from the organization's identity provider, issued for its own URL,
  and grants each tool by its own scope; it advertises them in its Protected
  Resource Metadata, and never logs a token. Without authorization it listens
  only on a loopback address ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **It ships in the container image**, and the release publishes both
  packages together. [Serving Workflows Over MCP](https://github.com/EldritchInc/azathoth/blob/main/docs/mcp.md) covers Claude Desktop, teams and the container
  ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).

### Upgrading From 1.1

Nothing changes for an existing installation. Upgrade, and run `azathoth init`
as after every upgrade:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

To serve workflows over MCP, install `azathoth-mcp` into the same venv. From
then on, upgrade both in one command: each release of it requires its own
minor release of `azathoth-ai`.

