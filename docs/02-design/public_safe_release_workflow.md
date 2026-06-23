# Public-Safe Release Workflow

- Status: current local MPL-2.0 public-core readiness workflow
- Date: 2026-06-23
- Source of truth: `docs/02-design/public_safe_release_workflow.plan.json`
- Safe default: keep all work local until explicit publication approval is given

This workflow records the current release-safety posture after the local MPL-2.0 public-core cleanup. It does not authorize publication, repository visibility changes, package or registry publishing, commits, pushes, PRs, tags, releases, or history rewriting.

## Current Goal

Graph Hub Core is prepared locally as an MPL-2.0 public-core codebase. The local release gate should pass without weakening `scripts/check_public_release.py` and without exposing project-specific research materials.

## Current Public Core

The public core includes:

- MPL-2.0 license and notice language for this repository's source code.
- Generic Graph Hub orchestration, MCP server, project config contracts, scaffold helpers, validation, render paths, artifact collection, and provenance surfaces.
- Public journal target formats: `nature`, `science`, `default`, `acs`, `rsc`, `elsevier`, `wiley`, and `cell`.
- Public-safe docs generated from live tool registries.
- Conservative release checker and regression tests.

Out of scope unless separately approved:

- Project-specific datasets, unpublished workflow notes, credentials, manuscript assets, and internal style packs.
- Public mirror creation, repository visibility changes, package or registry publication, release notes, tags, GitHub releases, commits, pushes, PRs, and history rewriting.
- Stable third-party plugin API promises or external code-loading guarantees.

## Verification Commands

Run these before claiming local readiness:

```bash
uv run python scripts/check_public_release.py
uv run python graphhub_mcp_server.py --smoke
uv run python scripts/gen_tool_reference.py --check
uv run python -m pytest tests/test_public_release_check.py tests/test_style_packs.py tests/test_presets.py -q
uv run python -m pytest tests/test_mcp_read_only.py tests/test_mcp_rendering.py tests/test_mcp_normalization.py tests/test_mcp_batch_quality.py -q
GIT_MASTER=1 git diff --check
GIT_MASTER=1 git status --short
```

Expected current behavior: the public release checker prints `public_release_check: ok` for the local working tree.

## Stop Conditions

Stop and ask before any action with external side effects or irreversible consequences: publication, visibility changes, package or registry upload, push, PR, commit, tag, release, history rewrite, or private material export.
