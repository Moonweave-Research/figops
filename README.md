# FigOps

FigOps is an MCP-native figure operations engine for reproducible research. It turns local CSV data, project configs, and plotting scripts into publication-oriented figures with explicit data contracts, provenance, artifact manifests, and local release gates.

"Data is the API. Quality is absolute."

## Start Here

- New user path: [docs/quickstart.md](./docs/quickstart.md)
- MCP client setup: [docs/mcp_setup.md](./docs/mcp_setup.md)
- Why FigOps: [docs/positioning.md](./docs/positioning.md)
- Generated MCP tool reference: [docs/tools.md](./docs/tools.md)
- Local QA and release gates: [docs/QA.md](./docs/QA.md)
- Contributor workflow: [CONTRIBUTING.md](./CONTRIBUTING.md)

## Local Quickstart

Run from the repository root:

```bash
uv sync
uv run python graphhub_mcp_server.py --smoke
uv run python orchestrator.py --project examples/synthetic_project --step plot --force
```

Expected output from the example render:

```text
examples/synthetic_project/results/figures/FigSynthetic_Response.png
```

For a copy-paste MCP render walkthrough, use [docs/quickstart.md](./docs/quickstart.md). For stdio client configuration, use [docs/mcp_setup.md](./docs/mcp_setup.md).

## What It Does

- Renders research figures from project-level `project_config.yaml` contracts.
- Validates declared CSV inputs and outputs before publishing artifacts.
- Applies public journal style targets: `nature`, `science`, `default`, `acs`, `rsc`, `elsevier`, `wiley`, and `cell`.
- Writes reproducibility metadata, runtime manifests, and figure manifest sidecars.
- Exposes MCP tools for local clients while keeping write tools disabled unless explicitly enabled.
- Keeps runtime state, generated artifacts, credentials, and environment caches outside tracked source by default.

## Public-Safe Examples

Each example uses synthetic or public-safe fixtures and runs from the repository root.

```bash
uv run python orchestrator.py --project examples/synthetic_project --step plot --force
uv run python orchestrator.py --project examples/multipanel_project --step plot --force
uv run python orchestrator.py --project examples/materials_polymer_recipe --step all --force
```

- [Synthetic project](./examples/synthetic_project/README.md): smallest configured CSV-to-figure path.
- [Multipanel project](./examples/multipanel_project/README.md): SVG panel assembly path.
- [Materials/polymer recipe](./examples/materials_polymer_recipe/README.md): domain helper analysis plus figure render.

## MCP Surface

FigOps ships a local stdio MCP server entrypoint backed by Graph Hub Core:

```bash
uv run python graphhub_mcp_server.py --smoke
uv run python graphhub_mcp_server.py doctor
```

The smoke command is self-contained and should report `"status": "ok"`. MCP write tools default to disabled; enable them only in a trusted local server configuration. See [docs/mcp_setup.md](./docs/mcp_setup.md) for client snippets and root policy.

## Local Release Gate

Before treating a local public-core checkout as ready, run:

```bash
uv run python scripts/check_public_release.py
uv run python graphhub_mcp_server.py --smoke
uv run python scripts/gen_tool_reference.py --check
uv run python -m pytest -q
```

Use focused tests and `uv run ruff check <changed Python files>` while iterating. The full gate is documented in [docs/QA.md](./docs/QA.md).

## Architecture

- `orchestrator.py`: CLI entrypoint for project orchestration.
- `graphhub_mcp_server.py`: thin MCP stdio and diagnostic entrypoint.
- `hub_core/`: config parsing, validation, cache logic, MCP tools, provenance, process execution, scaffolding, and runtime helpers.
- `analysis_helpers/`: shared R-side analysis utilities.
- `plotting/`: reusable plotting helpers and shared style logic.
- `themes/`: public journal style presets and profiles.
- `examples/`: public-safe runnable fixtures.

## License And Distribution Status

FigOps public-core source is licensed under the Mozilla Public License 2.0 (MPL-2.0). See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

Project-specific datasets, unpublished workflow notes, credentials, manuscript assets, and internal style packs are outside this public-core distribution unless explicitly included with their own notices.

## Operational Notes

- Prefer `uv run ...` for local commands in this checkout.
- Keep runtime state under `RESEARCH_HUB_RUNTIME_ROOT` or the default user cache, not inside the repository.
- Do not commit secrets, `.env` files, generated runtime outputs, or private project data.
- Use [AGENTS.md](./AGENTS.md) for repository operating rules and MCP environment trust policy.

**Last Update**: 2026-06-23 (public beta docs polish)
