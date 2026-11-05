# Azathoth MCP

Azathoth MCP serves promoted
[Azathoth](https://github.com/EldritchInc/azathoth) workflows as
[Model Context Protocol](https://modelcontextprotocol.io) tools, so an AI
client such as Claude Desktop, an IDE or your own agent can call them.

Only the workflows an operator lists are offered, each as one tool with the
name and description the operator wrote. Every call runs the workflow's
active production revision as a recorded, idempotent invocation, and returns
the invocation's ID with its result, so what an agent did can be traced to
its runs and evidence.

It runs over stdio for a local client, or over Streamable HTTP for a team,
as an OAuth 2.1 resource server in front of your organization's identity
provider.

[Serving Workflows Over MCP](https://github.com/EldritchInc/azathoth/blob/main/docs/mcp.md)
shows how to expose a workflow, connect Claude Desktop, and serve a team
behind your identity provider.

Azathoth MCP is released with Azathoth, at the same version, and requires
the same minor release of `azathoth-ai`. The design is recorded in
[ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md).

## License

MIT. See [LICENSE](https://github.com/EldritchInc/azathoth/blob/main/packages/azathoth-mcp/LICENSE).
