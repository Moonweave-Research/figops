# Public Safe Verification Report

Status: local MPL-2.0 public-core readiness verified
Date: 2026-06-23

This report supersedes the earlier planning-only blocked-state report. The user approved a local MPL-2.0 public-core cleanup. External publication, repository visibility changes, package or registry publishing, commits, pushes, PRs, tags, releases, and history rewrites remain out of scope.

## Verification Summary

The local public-core readiness gate is currently green:

- `uv run python scripts/check_public_release.py` -> `public_release_check: ok`
- `uv run python graphhub_mcp_server.py --smoke` -> health OK with 8 public style formats
- `uv run python scripts/gen_tool_reference.py --check` -> pass
- `uv run python -m pytest -q` -> 915 passed, 18 warnings, 48 subtests passed before the final blocker fixes
- Focused adapter/release tests -> pass before the final blocker fixes
- `GIT_MASTER=1 git diff --check` -> pass before the final blocker fixes

The final blocker-fix pass must rerun the relevant focused and broad checks after this report, preset-profile validation, and residual presentation-format cleanup.

## Current Public-Core Boundary

Included in the local public core:

- MPL-2.0 license and notice language for source files in this repository.
- Generic Graph Hub orchestrator, MCP server, validation, rendering, artifact, scaffold, and public style surfaces.
- Public journal target formats: `nature`, `science`, `default`, `acs`, `rsc`, `elsevier`, `wiley`, and `cell`.
- Conservative public release checker and tests.

Excluded unless separately approved:

- Project-specific datasets and unpublished research workflow notes.
- Credentials, manuscript assets, internal style packs, and private project markers.
- External publication, public mirror creation, package or registry publishing, visibility changes, pushes, PRs, tags, releases, and history rewriting.

## Remaining Follow-Up

- Rerun final verification after the latest blocker fixes.
- Review untracked planning artifacts before deciding whether to include, delete, or leave them untracked.
- Commit only if explicitly requested.
