# Public-Safe FigOps Evolution Spec

- Status: post-cleanup product evolution spec
- Date: 2026-06-23
- Scope: future public-safe evolution of Graph Hub into an installable MCP-native figure operations tool
- Working name: `FigOps` pending legal/trademark/package-name clearance

Graph Hub Core is now being prepared locally as an MPL-2.0 public-core codebase. `FigOps` remains a working title only. This spec does not authorize publication, package or registry publishing, repository visibility changes, commits, pushes, PRs, tags, releases, or history rewriting.

## Product Direction

Graph Hub should not be positioned as another Matplotlib style wrapper. The strongest public direction is an MCP-native figure operations system: inspect a research project, validate data and config contracts, render figures under controlled roots, collect artifacts, and leave reproducibility evidence behind.

Working tagline:

> Reproducible figure operations for research projects.

## Current Public-Core Foundation

Existing strengths that carry forward:

- MCP stdio server entrypoint through `graphhub_mcp_server.py`.
- Read-only MCP tools for health, discovery, style listing, project inspection, and validation.
- Write/render tools gated by explicit write-tool enablement.
- Root, runtime-root, allowed-data-root, and symlink safety model.
- Generated `docs/tools.md` from live MCP registries.
- Project-level contracts through `project_config.yaml`.
- Semantic data contracts, research-ops gates, provenance, artifact collection, and regression checks.
- Public journal formats: `nature`, `science`, `default`, `acs`, `rsc`, `elsevier`, `wiley`, and `cell`.

## Future Work

Future product gaps remain separate from local release readiness:

- Public name and package identity clearance.
- Install UX beyond clone/uv workflows.
- Host-specific MCP setup docs.
- Figure-level manifest, bundle, replay, retarget, and plotted-data capture as first-class product layers.
- A stable plugin/SPI, intentionally deferred until trust boundaries and support commitments are clear.

## Verification Commands

Current local readiness checks:

```bash
uv run python scripts/check_public_release.py
uv run python graphhub_mcp_server.py --smoke
uv run python scripts/gen_tool_reference.py --check
uv run python -m pytest -q
GIT_MASTER=1 git diff --check
GIT_MASTER=1 git status --short
```

Expected current behavior: the release checker prints `public_release_check: ok` for the local public-core working tree.

## Future Figure-Level Reproducibility Tests

- Manifest sidecar includes config/script/input/output/style/environment hashes.
- Bundle contains only approved public-safe files.
- Replay produces equivalent output.
- Retarget produces new style output without upstream analysis rerun.
- Plotted-data capture maps traces to exact data arrays or source columns.
- MCP render result returns artifact resources and manifest paths consistently.

## Adversarial Review Checklist

- No uncleared `FigOps` legal or package claim.
- No publication or visibility-change action without approval.
- No unsupported superiority claim over related tools.
- No private marker leakage.
- No plugin API promise before the gate.
- No figure-level reproducibility claim without tests.

## Stop Conditions

Stop before package publication, registry publication, repository visibility changes, public mirror creation, pushes, PRs, commits, tags, releases, private-material export, plugin API promises, or history rewriting.
