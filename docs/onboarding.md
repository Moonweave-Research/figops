# New Lab Member Path

Follow this sequence when you are new to Graph Hub.

1. Start with the [quickstart](quickstart.md). It creates a local scaffold and renders a CSV-backed
   figure without bespoke environment variables.
2. Run `uv run python graphhub_mcp_server.py doctor` and resolve any blocking errors. Optional
   dependency or disabled-write-tool warnings are normal until you need those capabilities.
3. Configure a local MCP client only after reading [mcp_setup.md](mcp_setup.md). Write tools remain
   disabled by default unless you intentionally enable them for a trusted local workspace.
4. Work through the [synthetic project tutorial](../examples/synthetic_project/README.md), the
   [multipanel tutorial](../examples/multipanel_project/README.md), and the
   [materials/polymer domain helper recipe](../examples/materials_polymer_recipe/README.md).
5. Use the generated [tool reference](tools.md) to inspect MCP inputs, outputs, plot types,
   semantic checks, and worked render examples.
6. Read [CONTRIBUTING.md](../CONTRIBUTING.md) before adding plot types, MCP tools, or docs.
7. For environment trust and root-widening policy, read the MCP Env Trust Model section in
   [AGENTS.md](../AGENTS.md#10-mcp-env-trust-model).

After this path, you should be able to scaffold a project, render a figure, inspect tool schemas,
and understand the local verification gate used before every PR.
