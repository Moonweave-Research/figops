# Changelog

All notable changes to Graph Hub are documented here.

This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## Release Process

- Keep the `[project] version` field in `pyproject.toml` as the single package version.
- Every release PR updates this changelog and makes the version bump deliberate.
- Use `MAJOR.MINOR.PATCH`: major for incompatible public contract changes, minor for new
  backward-compatible capabilities, and patch for backward-compatible fixes.
- Run the local release gate before opening a release PR: `uv run python -m pytest -q`,
  changed-file `uv run ruff check ...`, and `uv run python graphhub_mcp_server.py --smoke`.
- Maintainers tag releases after merge; implementers open PRs but do not merge or tag.

## [0.6.0] - 2026-06-20

### Added

- M4.1 multi-series broken-axis rendering now preserves per-series styling, legends,
  error bars, and overlays; the earlier P1c refusal guard was removed.
- M4.2 plot coverage now includes registered box plots, violin plots, faceting /
  small-multiples, statistical overlays (fit line, CI band, and significance markers),
  and grouped-bar mean / median replicate aggregation.
- M4.3 materials/polymer domain analysis helpers provide reusable, contract-validated
  analysis steps for common signal processing and material-physics transforms.
- M4.4 richer semantic data contracts add monotonic, monotonic-within-group,
  exact and ranged expected sample counts, and unit-coherence checks.

### Changed

- The `graphhub.describe` discovery surface now exposes the expanded semantic-check
  vocabulary so agents can discover data-contract capabilities from the live registry.

## [0.5.0] - 2026-06-19

### Added

- M5.1 registry-backed `graphhub.describe` discovery for plot types, MCP tool schemas,
  semantic checks, and worked render examples.
- M3 adapter layer for prefetch, Athena, and project conventions, with generic defaults
  and opt-in bespoke integrations.
- M3 plot-type registry and render-backend interface, so new plot types register through
  `PLOT_TYPES` instead of hardcoded dispatch lists.
- M3 config schema versioning and migration support for project configs.
- M3 root/runtime configuration trust model for MCP server roots and allowed data roots.

### Changed

- M1 decomposed the MCP surface into focused modules under `hub_core/mcp/`.
- M2 strengthened fundamentals around transport safety, error behavior, public-release
  checks, and reproducibility gates.
- MCP discovery, validation, and self-description now share live registries to reduce
  schema drift.

### Security

- Root and runtime configuration now validate trust-boundary widening inputs before
  they affect MCP data access.
