# MCP Setup

FigOps exposes a local stdio MCP server through `graphhub_mcp_server.py`. The server is backed by Graph Hub Core and designed
for local research workspaces: read-only discovery is safe by default, and write tools default to disabled.

## Verify The Server

Run from the repository root:

```bash
uv run python graphhub_mcp_server.py --smoke
uv run python graphhub_mcp_server.py doctor
```

The smoke command should report `"status": "ok"`. `doctor` may report optional dependency warnings;
resolve only the warnings that affect the tools you intend to use.

## Stdio Client Command

Use this command shape in MCP clients that accept a command plus args:

```json
{
  "command": "uv",
  "args": ["run", "python", "graphhub_mcp_server.py"],
  "cwd": "/absolute/path/to/figops"
}
```

If your client does not support `cwd`, wrap the command in a small launcher script outside the repo
that changes to the FigOps checkout before starting `uv run python graphhub_mcp_server.py`.

## Write-Tool Policy

MCP write tools default to disabled. Enable them only for a trusted local workspace where the MCP
client and selected project roots are under your control.

Use server configuration or explicit CLI values when available. Environment variables remain a
supported operator-policy source, but they must not silently widen access:

- `GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED`: enables tools that write files or launch render jobs.
- `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS`: adds allowed read roots beyond the research root and runtime root.
- `GRAPH_HUB_MCP_STRICT_ROOTS`: refuses broad allowed roots such as `/` or a home directory.
- `RESEARCH_HUB_RUNTIME_ROOT`: selects where MCP jobs, manifests, logs, and generated artifacts are stored.

For the canonical trust model, read [AGENTS.md](../AGENTS.md#10-mcp-env-trust-model).

## Useful First Tools

After connecting a client, start with:

- `graphhub.health`: server health, configured roots, and policy warnings.
- `graphhub.describe`: public style formats, plot types, and tool surface summary.
- `graphhub.list_styles`: accepted target formats and profiles.
- `graphhub.render_csv_graph`: CSV-to-figure render path when write tools are explicitly enabled.

The full generated schema reference is [tools.md](tools.md).
