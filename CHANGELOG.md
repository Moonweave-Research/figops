# Changelog

All notable changes to FigOps are documented here.

This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## Release Process

- Keep the `[project] version` field in `pyproject.toml` as the single package version.
- Every release PR updates this changelog and makes the version bump deliberate.
- Use `MAJOR.MINOR.PATCH`: major for incompatible public contract changes, minor for new
  backward-compatible capabilities, and patch for backward-compatible fixes.
- Run the local release gate before opening a release PR: `uv run python -m pytest -q`,
  changed-file `uv run ruff check ...`, and `uv run python figops_mcp_server.py --smoke`.
- Maintainers tag releases after merge; implementers open PRs but do not merge or tag.

## [0.17.8] - 2026-06-25

### Added

- Add provenance-aware journal preflight metadata and a style report CLI so official journal guidance, Graph Hub assumptions, and internal policies are distinguishable.

### Changed

- Preserve existing preflight result compatibility while attaching provenance, enforcement, and source metadata to each check.

## [0.17.7] - 2026-06-25

### Added

- Add shaded-region / target-zone annotation support to CSV graph rendering and MCP render inputs.

## [0.17.6] - 2026-06-25

### Fixed

- Match CSV-graph annotation text size to active style tokens so annotation renders no longer trip `font_size_token_drift`.
- Clip annotation text and arrows to their axes so edge callouts no longer expand tight bounding boxes and collapse narrow figures.

## [0.17.5] - 2026-06-25

### Added

- Add log-scale axis options, series splitting, and annotations for `figops.render_csv_graph` scatter/line/xy renders.
- Add a geometry diagnostic for figure-title to facet-panel-title overlap.

### Fixed

- Reserve headroom for facet suptitles so panel headers no longer collide with the figure title.
- Embed and preserve PNG DPI metadata during journal saves and provenance fingerprinting.

## [0.17.4] - 2026-06-24

### Added

- Add a manual GitHub Actions Trusted Publishing workflow for TestPyPI/PyPI uploads.
- Document exact PyPI/TestPyPI pending publisher values and install-smoke steps.

### Changed

- Update public distribution docs and README to point at Trusted Publishing instead of direct token-based uploads.

## [0.17.3] - 2026-06-24

### Fixed

- Include a public packaged scaffold template so installed `figops --init` works from wheel installs.
- Require explicit distribution-policy approval in the guarded PyPI uploader.
- Scan packaged R helper files for private release markers.

## [0.17.2] - 2026-06-24

### Changed

- Switch FigOps licensing metadata and repository license files to Apache-2.0 for public package distribution.
- Split the PyPI upload guard from the private repository scan so uploads are blocked by package-artifact and license checks rather than private internal docs that are not shipped.

## [0.17.1] - 2026-06-24

### Added

- Add a public-release clearance checklist for license/IP review and private-surface separation before PyPI upload.
- Add an optional structured blocker listing to the public-core status reporter so the remaining gate work can be reviewed by family.

## [0.17.0] - 2026-06-24

### Changed

- Rename the install distribution and primary console scripts to FigOps:
  `figops`, `figops-mcp`, and `figops.*` MCP tools are now the primary public
  identity.
- Preserve legacy `graphhub` / `graphhub-mcp` console aliases and
  `graphhub.*` MCP tool aliases for compatibility while current docs and
  generated references move to the FigOps name.

## [0.16.11] - 2026-06-24

### Changed

- Rewrite the README around a more human install/use/distribution story,
  including the current GitHub Release wheel path and remaining public-release gate.

## [0.16.10] - 2026-06-24

### Added

- Add a GitHub release asset smoke checker that verifies the current wheel and
  source distribution are attached to the matching release tag.

## [0.16.9] - 2026-06-24

### Added

- Add a consumer-style wheel install smoke that runs installed `graphhub` and
  `graphhub-mcp` console commands through an isolated `uv run --with` path.

## [0.16.8] - 2026-06-24

### Added

- Add a package metadata smoke checker for built distributions, covering PyPI
  name, version, author, maintainer, and console script entry points.

## [0.16.7] - 2026-06-24

### Changed

- Split internal style/profile marker literals out of packaged runtime source
  while preserving the existing internal target-format and profile contracts.

## [0.16.6] - 2026-06-24

### Added

- Add a public-package artifact surface checker for built wheel/source
  distributions.
- Add a `MANIFEST.in` that keeps private docs, tests, examples, and repository
  operating files out of source distributions.

## [0.16.5] - 2026-06-24

### Added

- Add a machine-readable public-core inventory for candidate public surfaces,
  private/internal blockers, and release exit criteria.
- Add a JSON status reporter that combines the inventory with the live public
  release gate blocker families.

## [0.16.4] - 2026-06-24

### Added

- Add a fail-closed guarded TestPyPI/PyPI upload wrapper that runs the public
  release gate before constructing or executing `twine upload`.
- Update PyPI readiness docs to route uploads through the guarded wrapper.

## [0.16.3] - 2026-06-24

### Added

- Add Python packaging metadata for wheel/source-distribution builds, including
  package discovery, owner metadata, license files, repository URLs, and
  `graphhub` / `graphhub-mcp` console entry points.
- Document the PyPI/TestPyPI release boundary and keep public uploads blocked
  until the repository license and public release gate are ready.

## [0.16.2] - 2026-06-23

### Fixed

- `hub_uv.py` now boots without importing dependency-heavy `hub_core` package
  initialization before uv has created the project environment.
- MCP project rendering now runs data-contract preflight before snapshot/render
  execution, matching the CLI fail-fast path for missing declared inputs.
- Public release checks now block post-tag commits that keep package and changelog
  metadata at the already-tagged version.

## [0.16.1] - 2026-06-22

### Changed

- MCP render handlers are split into focused CSV, project-render, and validation
  mixins while preserving the public tool contract through the server aggregator.
- MCP render artifact helpers now share manifest/status writing and lock-status
  provenance plumbing across CSV and project render paths.
- Internal MCP symlink aliases are allowed when they stay within trusted roots;
  true root escapes remain rejected.

### Fixed

- Failure render manifests now record the generated manifest/status paths before
  the manifest is written, so `created_paths` round-trips accurately.
- Local generated artifact directories are ignored so demo, agent, and browser
  traces do not pollute git status.

## [0.16.0] - 2026-06-22

### Added

- `project.status: active | legacy`. Legacy projects are excluded from the
  runnable/render/research-ops-enforcement surface while remaining discoverable
  and inspectable, so superseded measurement projects can be retired without
  deleting or renaming their data (#161).
- Opt-in `GRAPH_HUB_MCP_STRICT_DATA_ROOTS` to require explicitly listed MCP data
  roots, and `GRAPH_HUB_RUNTIME_ROOT` as a launcher-compatible fallback for
  runtime storage root selection (#160).

### Changed

- Journal compliance floors (minimum font size, line width, figure height) now
  apply under every profile rather than only `baseline`, and explicit per-artist
  sub-floor sizes are clamped to the floor at draw time with a warning instead of
  being emitted silently (#159).
- `doctor` now performs real research_root/runtime_root filesystem checks and
  labels write tools as "enabled (not execution-verified)"; broad-data-root
  detection covers multi-user parent directories such as `/Users` and `/home`
  (#160).

### Fixed

- Geometry diagnostics no longer report `passed: true` when every eligible check
  was skipped (now reports `None`); bar plots with replicate aggregation plus an
  error column no longer crash (standard error is recomputed); `category_order`
  is rejected for plot types that do not support it instead of being silently
  ignored; `artists_outside_axes` reports an informational crop fraction on
  explicit limits instead of passing clean (#159).
- Documentation drift corrected across `docs/architecture.md`, `docs/ROADMAP.md`,
  `AGENTS.md`, and `task.md` to match the shipped v0.15.0 reality (#157).

## [0.15.0] - 2026-06-21

### Changed

- Research-operations rules now enforce by default for `project.role: module`
  projects across both CLI and MCP render paths: raw-integrity drift blocks
  renders, placeholders are forbidden, declared figure traceability chains are
  validated, and declared canonical docs must exist. Explicit `false` opt-outs
  remain available for scoped relaxation (#151).

### Fixed

- MCP server startup now honors the documented
  `GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED` environment variable by seeding server
  config from `McpServerConfig.from_env()` (#149).
- MCP rendering tests now isolate `RESEARCH_HUB_RUNTIME_ROOT` so runtime-root
  state does not leak across test runs (#149).
- MCP and discovery config reads now use the duplicate-key-rejecting YAML
  loader, including restored YAML merge-key support and conservative warnings
  for near-miss top-level config keys (#150).
- Data-read path validation now applies a symmetric symlink guard, and the
  test suite uses a global hermetic runtime-root fixture (#150).

## [0.14.0] - 2026-06-21

### Added

- Research-operations philosophy Tier 3 hygiene, documented in
  `docs/specs/research_ops_philosophy.md`, completes research-ops philosophy
  Tiers 1-3.
- Quarantine and archive zone recognition now excludes `_archive`,
  `_quarantine`, `_cross_validation`, `legacy_*`, `*_legacy`, and `*.bak*`
  paths from runnable discovery by default, with `include_quarantine` opt-in
  and advisory naming-convention linting (#145).
- Machine-readable ordered `canonical_docs` precedence registry adds
  existence checks, advisory by default with opt-in `require_canonical_docs`
  strict mode (#146).
- Config placeholder detection now catches TODO, FIXME, TBD, and related
  placeholders as advisory findings, with opt-in `forbid_todo_placeholders`
  strict mode (#147).

## [0.13.0] - 2026-06-21

### Added

- Research-operations philosophy Tier 2 traceability and provenance,
  documented in `docs/specs/research_ops_philosophy.md`, adds an opt-in
  `sample_registry` with unique sample ids and condition-reference integrity
  validation (#141).
- Figure, data, and claim traceability now supports figure `claim`,
  `samples`, and `conditions` metadata with registry / condition reference
  validation, opt-in `require_figure_traceability`, and an inspect
  traceability matrix (#142).
- Opt-in raw-data immutability via `data_contract.raw_integrity` now supports
  sha256 manifest seal / verify, orchestrator preflight warn / strict modes,
  and inspect status reporting (#143).

## [0.12.0] - 2026-06-21

### Added

- Research-operations philosophy enforcement Tier 1, documented in
  `docs/specs/research_ops_philosophy.md`, now distinguishes `project.role`
  master and module projects and refuses master-root execution (#137).
- Machine-readable `folder_roles` taxonomy classifies raw reservoirs,
  reference, theory, docs, support, and archive folders, then filters them out
  of the re-run surface so only runnable project areas remain (#138).
- Structural validation now covers `experimental_conditions`, which were
  previously ignored, including unique condition ids and inspect-surfaced
  summaries (#139).

## [0.11.1] - 2026-06-21

### Changed

- Aligned the `nature` track figure column widths to Nature Communications
  (single 88 mm, double 180 mm), matching the project's Nature Communications
  baseline target (#135).

## [0.11.0] - 2026-06-21

### Added

- Explicit faceting layout control now supports `facet_ncols` and
  `facet_nrows` for data-driven small multiples, including exact 2 / 3 / 4
  column or row grids, an automatic column cap raised from 3 to 5, and
  fail-fast validation of invalid grids (#132).

### Changed

- Maintenance: cleared all pre-existing repo-wide ruff lint findings, so
  `ruff check .` now passes with 0 errors; this was limited to whitespace,
  import-order, line-wrapping, and unused-import cleanup with no behavior
  change (#133).

## [0.10.0] - 2026-06-20

### Added

- Per-journal compliance tokens now encode minimum font size, minimum line
  width, and maximum figure height from each journal's official figure
  guidelines, with clamp-with-warning enforcement so sub-spec output is not
  silently emitted (#130).
- A new `journal_compliance` geometry diagnostic reports journal guideline
  compliance, and RSC / Elsevier tick sizing now honors their 7 pt floor
  (#130).

### Fixed

- Journal column widths now match official figure guidelines: Science
  57 / 121 / 184 mm, ACS single 84.67 mm (240 pt / 3.33 in), and Wiley /
  Advanced Materials 85 / 178 mm (#129).
- Cell Press style now uses Arial as its primary font per Cell figure
  guidelines (#129).

## [0.9.0] - 2026-06-20

### Added

- Per-journal style tracks now cover Cell Press (single 85 mm, 1.5-column
  114 mm, double 174 mm), RSC (single 83 mm, double 171 mm), and Elsevier
  (single 90 mm, 1.5-column 140 mm, double 190 mm), each with distinct
  widths, sans-serif font scale, marker / line tokens, and viridis default
  colormap (#125, #126, #127).
- Distinct style tracks now exist for all seven journal `target_format`
  profiles: nature, science, acs, wiley, cell, rsc, and elsevier (#125,
  #126, #127).

## [0.8.0] - 2026-06-20

### Added

- Per-journal style tracks now provide distinct figure widths, font scales,
  marker tokens, and colormaps for Science / AAAS (55 / 120 / 183 mm), ACS
  (82.55 / 177.8 mm), and Wiley / Advanced Materials (84 / 174 mm) (#120,
  #121, #122).

### Changed

- Smart legend placement is now collision-aware across journal tracks and
  relocates legends, including a top-outside fallback, when the preferred
  position would overlap plotted data (#123).

## [0.7.0] - 2026-06-20

### Added

- Faceted rendering now supports fixed and free `facet_scales` options (#114).
- Categorical plots accept explicit `category_order` and `facet_order` overrides while
  preserving input order by default (#116).
- Heatmaps support `annotate_values`, and single-series bar plots support
  `bar_error_column` error bars (#118).

### Changed

- Nature Communications baseline styling adds marker-size tokens and axis margins to
  prevent marker clipping (#113).
- Violin plots use smoother KDE behavior while preserving the small-sample fallback (#115).

### Fixed

- Legend and title placement now avoids overlapping rendered plot content (#112).
- Geometry diagnostics are tuned to reduce false-positive overlap warnings (#117).

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
