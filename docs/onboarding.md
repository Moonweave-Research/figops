# New Lab Member Path

Follow this sequence when you are new to FigOps.

1. Start with the [quickstart](quickstart.md). It creates a local scaffold and renders a CSV-backed
   figure without bespoke environment variables.
2. In a source checkout, run `python hub_uv.py --print-env`, then
   `python hub_uv.py run python figops_mcp_server.py --hub-path . --research-root . --runtime-root .omo/evidence/task-6-runtime doctor --json`
   and resolve any blocking errors. For an installed package, run `figops-mcp doctor`.
   Optional I/O, missing-`Rscript`, or disabled-write-tool warnings are normal until
   you need those capabilities. Missing `uv` on `PATH` blocks the source-checkout
   wrapper; missing `pytest` means local source-checkout tests have not been verified.
3. Work through the [synthetic project tutorial](../examples/synthetic_project/README.md), the
   [multipanel tutorial](../examples/multipanel_project/README.md), and the
   [materials/polymer domain helper recipe](../examples/materials_polymer_recipe/README.md).
4. Use the generated [tool reference](tools.md) to inspect MCP inputs, outputs, plot types,
   semantic checks, and worked render examples.
5. Read [CONTRIBUTING.md](../CONTRIBUTING.md) before adding plot types, MCP tools, or docs.
6. For environment trust and root-widening policy, read the MCP Env Trust Model section in
   [AGENTS.md](../AGENTS.md#10-mcp-env-trust-model).

After this path, you should be able to scaffold a project, render a figure, inspect tool schemas,
and understand the local verification gate used before every PR.
