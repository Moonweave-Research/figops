# QA Guide

This document defines the local quality gate for the independent `figops` repository.
Routine users should start with [quickstart.md](quickstart.md); use this guide before PRs, release
checks, or public-core readiness reviews.

## Public-Core Local Gate

Run from the repository root:

```bash
uv run python scripts/check_public_release.py
uv run python graphhub_mcp_server.py --smoke
uv run python scripts/gen_tool_reference.py --check
uv run python -m pytest -q
```

Expected results:

- `public_release_check: ok`
- MCP smoke reports `"status": "ok"` and the expected public style count.
- `docs/tools.md` matches the live MCP registry.
- The pytest suite exits with status 0.

While iterating on Python changes, also run focused tests and ruff on the changed files, for example:

```bash
uv run ruff check graphhub_mcp_server.py hub_core tests
uv run python -m pytest tests/test_public_beta_docs.py -q
```

## Example Smoke Runs

These public-safe fixtures exercise the user-visible render paths without private data:

```bash
uv run python orchestrator.py --project examples/synthetic_project --step plot --force
uv run python orchestrator.py --project examples/multipanel_project --step plot --force
uv run python orchestrator.py --project examples/materials_polymer_recipe --step all --force
```

Expected outputs:

- `examples/synthetic_project/results/figures/FigSynthetic_Response.png`
- `examples/multipanel_project/results/figures/FigSynthetic_Multipanel.svg`
- `examples/materials_polymer_recipe/results/figures/polymer_domain_helper.png`

## Regression And Integrity Criteria

FigOps quality checks focus on:

- Semantic data contracts: declared CSV checks and semantic ranges must pass before trusted renders.
- Artifact integrity: generated figures must be non-empty and match their declared format headers.
- Determinism: provenance and lockfile hashes are recorded for reproducible reruns.
- Runtime separation: generated outputs, caches, credentials, and local runtime state stay outside tracked source unless an example explicitly owns a fixture.
- MCP trust boundaries: root-widening and write-tool settings follow the MCP Env Trust Model in [AGENTS.md](../AGENTS.md#10-mcp-env-trust-model).

## Operator Checks

For broader local operations, use the orchestrator checks that match your project set:

```bash
uv run python orchestrator.py --list-projects
uv run python orchestrator.py --check-all --step plot --strict-lock --regression-baseline check
uv run python orchestrator.py --check-all --step diagrams --strict-lock
```

These commands may require configured local projects and runtime dependencies beyond the public-safe examples.

**Last Update**: 2026-06-23 (public-core local gate alignment)
