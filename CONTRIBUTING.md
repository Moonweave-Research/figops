# Contributing

FigOps is developed as a local-first research figure-operations tool. GitHub Actions
is currently disabled, so local verification is the merge gate.

## Architecture

Read [docs/architecture.md](docs/architecture.md) before changing module boundaries. The short
version:

- `graphhub_mcp_server.py` is a thin CLI/stdio entrypoint.
- `hub_core/mcp/` owns MCP transport, schemas, server wiring, tools, resources, prompts, security,
  and render orchestration.
- `hub_core/rendering/` owns the plot-type registry and render backend interface.
- `hub_core/adapters/` owns optional bespoke integrations. Defaults must stay generic/noop/null.

## Add a Plot Type

1. Add one `PlotType` entry to `PLOT_TYPES` in `hub_core/rendering/registry.py`.
2. Provide the renderer callable, `arg_schema`, and `capabilities`.
3. Add or update tests proving the new type appears in `graphhub.describe`, the
   `graphhub.render_csv_graph` schema enum, and the JSON-RPC validator.
4. Add a small render witness when behavior changes.

Do not add a second hand-maintained plot-type list. The registry feeds discovery, validation,
and generated docs.

## Add an MCP Tool

1. Add the tool name and handler mapping in `hub_core/mcp/schemas.py`.
2. Add one `ToolDefinition` with input and output schemas.
3. Implement the handler in the appropriate `hub_core/mcp/tools/` module.
4. Add tests for `tools/list`, `tools/call` validation, and handler behavior.
5. Regenerate the tool reference:

```bash
uv run python scripts/gen_tool_reference.py --write
```

The staleness test fails if `docs/tools.md` does not match the live registry.

## TDD and Review Workflow

- Start with a failing witness for behavior changes.
- Keep one logical change per PR.
- Preserve existing architecture and style unless the task requires a change.
- Use review-until-clean: inspect the diff, run focused tests, run the full suite, then address
  correctness or missing-test findings before opening the PR.
- Never leave TODO stubs or silent fallbacks.

## Local Gate

Run commands through `uv run`.

Required before every PR:

```bash
uv run python scripts/check_public_release.py
uv run python graphhub_mcp_server.py --smoke
uv run python scripts/gen_tool_reference.py --check
uv run python -m pytest -q
```

Also run ruff on changed Python files, for example:

```bash
uv run ruff check scripts/gen_tool_reference.py tests/test_tool_reference_docs.py
```

Each PR body should include the exact tail from the local gate. When dependencies are not part of
the task, do not edit dependency declarations or commit lockfile churn.

## Security and Environment Trust

Do not commit secrets, `.env` files, API keys, tokens, private URLs, session cookies, or local
runtime outputs. Before pushing, run a secret scan when available.

For MCP root and environment policy, link to the canonical MCP Env Trust Model in
[AGENTS.md](AGENTS.md#10-mcp-env-trust-model) rather than duplicating the policy.
