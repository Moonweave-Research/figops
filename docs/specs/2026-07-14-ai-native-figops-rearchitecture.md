# AI-Native FigOps Rearchitecture — Single Source of Truth

> Status: **Complete; real-R execution remains unavailable on this host because `Rscript` is absent**<br>
> Date: 2026-07-14<br>
> Scope: FigOps kernel, MCP agent surface, evidence/readiness, plotting defaults,
> compatibility adapters, tests, and migration<br>
> Owner: Research Hub Commander<br>
> Governing principle: **Catch what the LLM misses without reducing the LLM's
> capability.**

This is the only implementation plan for the AI-native FigOps rearchitecture.
Later agents update the execution checklist and decision log in this file rather
than creating competing plans. `docs/architecture.md` and `docs/ROADMAP.md`
continue to describe shipped state and must be updated when a work package
ships. Historical plans remain historical.

## 1. Decision and problem statement

FigOps already has a valuable kernel: isolated execution, project contracts,
data validation, provenance, style presets, artifact collection, geometry
measurements, and regression evidence. The problem is the boundary presented to
an LLM.

The current agent surface spends too much contract and context on prescribing
plot decisions that capable LLMs can make, while several failure modes that an
LLM is likely to miss are incomplete or fail open. The result is inverted
leverage:

- aesthetic choices are encoded in a large plotting DSL and mandatory call
  choreography;
- visual inspection is discouraged and rendered images are not exposed as MCP
  resources;
- labels and style can be silently changed after the LLM has made its decision;
- path containment, artifact state, provenance completeness, raw-integrity
  sealing, and statistical-claim provenance have gaps;
- objective measurements, policy judgments, and human approval are partially
  collapsed into the same pass/fail field.

The rearchitecture therefore keeps and strengthens the kernel while replacing
the default agent experience with a thin, evidence-first surface.

### 1.1 Product invariant

FigOps must do all of the following:

1. Preserve the LLM's ability to interpret data, choose a plot, author
   project-local Python/R plotting code, compose a figure, and inspect the
   rendered image.
2. Reliably catch boundary, integrity, provenance, unit, data-contract,
   artifact, and unsupported-claim failures that the LLM may overlook.
3. Report measurements as evidence. Apply publication or lab preferences only
   through an explicit policy pack.
4. Never silently change scientific text, data meaning, or an authored visual
   decision.
5. Never equate automatic success with human publication approval.

### 1.2 Design tests for every proposed control

A control belongs in the kernel only if at least one is true:

- it protects a trust boundary;
- it proves artifact/data/provenance integrity;
- it enforces an explicit scientific or runtime contract;
- it prevents silent failure or unsafe mutation;
- it produces bounded objective evidence.

If a control instead chooses hierarchy, composition, annotation placement,
palette, plot type, visual emphasis, or rhetoric, it belongs to the LLM unless
an explicit policy pack requests it. If the decision is scientific acceptance
or final venue suitability, it belongs to a human.

## 2. Ownership matrix

| Concern | LLM owns | Kernel owns | Explicit policy owns | Human owns |
|---|---|---|---|---|
| Data interpretation | hypotheses, relevant variables, grouping, intended comparison | bounded profile, dtype/null/range/cardinality facts | required metadata or domain bounds | whether interpretation is scientifically defensible |
| Plot selection | plot type, encoding, composition, hierarchy | capability discovery and safe execution | allowed output formats or mandated venue constraints | final communication choice |
| Plot implementation | project-local Python/R code and targeted revisions | contained snapshot execution, timeout, declared I/O verification | approved runtime/language restrictions | acceptance of authored result |
| Scientific labels | exact display text and explicit label map | raw preservation, mapping provenance, collision evidence | lab naming conventions when selected | whether abbreviations are acceptable |
| Statistical annotations | whether and how to present a supported result | require cited calculation evidence and hashes | permitted tests/models or venue notation | validity of inference and claim |
| Layout and aesthetics | spacing, emphasis, legend placement, palette selection | objective clipping/extent/contrast measurements | minimum fonts/lines, safe-zone or accessibility rules | final aesthetic/venue judgment |
| Data and filesystem safety | consume the available evidence | containment, symlink defense, regular-file checks, size/time limits | allowed roots and write enablement | authorization to widen scope or mutate source |
| Artifact quality | inspect preview and revise | existence, format/header, dimensions, hashes, declared outputs | baseline/tolerance policy | final approval |
| Reproducibility | choose meaningful inputs and code | Git/config/environment/input/script/output fingerprints | required reproducibility level | whether evidence is sufficient for release |
| Publication readiness | reason from evidence | deterministic evidence collection and hard integrity gates | journal/lab readiness rubric | approval and submission decision |

## 3. Verified current-state evidence and P0 defects

Line references in this section identify the 2026-07-14 source baseline. Tests,
not line numbers, become the durable contract after patching.

### P0-1 — `data_contract.csv_checks[].path` can escape the project boundary

Evidence:

- `hub_core/config_parser.py:551-563` checks only that `path` is a non-empty
  string; it does not reject absolute paths, `..`, or symlink escape.
- `hub_core/utils.py:12-14` returns an absolute input unchanged and otherwise
  joins and normalizes without containment.
- `hub_core/data_contract.py:173-210` resolves and prefetches that path during
  preflight.
- `hub_core/data_contract.py:217-249` resolves, checks, prefetches, and later
  reads it during validation.
- `hub_core/mcp/tools/render_project.py:99-124` invokes both validators in the
  MCP project-render path.

Required correction: one lower-layer resolver must require a project-relative
path, reject traversal and symlink components/targets that escape, optionally
require an existing regular file, and be used at config validation and again at
the read/prefetch boundary. Validation must fail closed.

### P0-2 — default label handling silently changes scientific identifiers

Evidence:

- `plotting/bridge_renderer.py:222-243` sets `compress_labels=True` by default.
- `plotting/renderers/labels.py:18-22` applies `compress_sample_label` to display
  labels when enabled.
- `plotting/utils.py:77-103` replaces underscores and project-specific terms,
  so an identifier such as `ABC_DEF` can render differently from the source.
- `hub_core/mcp/schemas.py:427-483` exposes no raw-preserving/label-map choice in
  `figops.render_csv_graph`.

Required correction: raw-preserving display is the core and v2 default. Any
transformation requires an explicit mode or `label_map`; the manifest records
the original-to-display mapping and transformation identifier. A documented
legacy transform remains available only for reproduction/compatibility.

### P0-3 — readiness ignores decisive artifact/provenance evidence and rejects a producer-valid status

Evidence:

- `hub_core/publication_evidence.py:42-51` allowlists `artifact_status`,
  `failure_stage`, and baseline evidence; `publication_evidence.py:162-168`
  also extracts provenance hashes.
- `hub_core/publication_readiness.py:374-465` evaluates geometry, calculation,
  preflight, layout, and an optional data-contract payload, but does not gate on
  `artifact_status`, `failure_stage`, baseline declaration, or provenance.
- `hub_core/publication_readiness.py:317-327` accepts only `passed`, `failed`, or
  `skipped` calculation status.
- `hub_core/data_contract_semantic_grouped.py:357-385` legitimately emits
  `status="warning"` with `manual_review_needed=True` for `warn_only` grouped CV.
- `tests/test_publication_readiness.py:209-216` currently encodes `warning` as an
  invalid hard block, preserving the producer/consumer mismatch.

Required correction: define and validate a producer-owned evidence envelope.
Failed/missing/corrupt artifacts, a non-empty failure stage, and missing required
provenance are hard gates. `warning` is a supported non-hard status and maps to
review/revision according to explicit policy. `passed=None` or a skipped metric
must mean “not measured” with severity determined by that metric's policy, not a
universal malformed-evidence failure.

### P0-4 — the agent is prevented from using its visual capability

Evidence:

- `docs/internal/protocols/00_agent_graph_workflow.md:33-36` tells agents not to
  read images and to stop when visual judgment is required.
- `hub_core/mcp/resources.py:23-69` exposes style/profile/project config and job
  manifest resources, but no rendered figure preview.
- `hub_core/mcp/schemas.py:636-659` makes artifact collection metadata-only.

Required correction: every successful raster-capable render returns a bounded
preview resource URI. Add a contained, MIME-checked job artifact resource. The
default loop becomes `render -> objective evidence -> LLM image inspection ->
targeted revision`. Human review remains required for final approval, not for
allowing the LLM to look.

### P0-5 — strict raw integrity can report success when no seal exists

Evidence:

- `hub_core/raw_integrity.py:63-80` resolves configured integrity mode.
- `hub_core/raw_integrity.py:81-92` returns `sealed=False` and `ok=True` when the
  manifest is missing, including when the resolved mode is `strict`.

Required correction: a configured strict mode without a valid seal is
`ok=False`; warn mode remains non-blocking but explicit. Runtime render and
readiness tests must witness this behavior.

### P0-6 — examples can invent statistical claims without provenance

Evidence:

- `hub_core/mcp/schemas.py:146-178` auto-generates a linear fit, CI band, and a
  `p<0.05` significance marker in worked examples.
- `hub_core/mcp/schemas.py:462-465` accepts fit and significance inputs while
  `significance_markers` is an unstructured object list.
- The render validator checks renderability, not whether the displayed
  statistical claim points to a calculation artifact.

Required correction: remove invented inferential claims from examples. A
significance annotation must reference a calculation check/evidence ID and
analysis artifact hash with test/model metadata. Missing provenance blocks the
annotation, not the whole non-statistical figure.

## 4. High-priority design debt addressed by this plan

These are not all security P0s, but they directly reduce agent capability or
generate misleading confidence.

1. **Overspecified render DSL.** `figops.render_csv_graph` has 46 top-level
   input properties (`hub_core/mcp/schemas.py:432-482`); each multipanel panel
   repeats 30 properties (`schemas.py:511-545`). The generated `docs/tools.md`
   is 129,241 bytes and 6,264 lines on this baseline.
2. **Missing bounded data inspection.** Rendering requires exact column names,
   but the 14 canonical tools in `hub_core/mcp/schemas.py:31-46` contain no
   data-profile tool.
3. **Mandatory ceremony.** `hub_core/mcp/prompts.py:31-38` and `:103-111`
   prescribe dry-run/render/collect chains even though renders already validate
   and dry-runs produce no visual evidence.
4. **Measurement and policy are collapsed.**
   `hub_core/geometry_diagnostics.py:110-181` combines hard and advisory metrics
   into one aggregate `passed`; `hub_core/publication_readiness.py:28-49`
   hard-blocks some aesthetic heuristics.
5. **Font-token exactness overreaches.**
   `hub_core/geometry_style_checks.py:52-123` fails on any non-token font size
   and on multiple sizes in the same broad role, not only a declared minimum.
6. **Hidden post-processing.** `themes/journal_theme.py:583-602` applies profile
   overrides, compliance clamping, then overwrites the series palette with
   Okabe-Ito; `journal_theme.py:756-763` can declutter and clamps live artists at
   save time without a persisted before/after change set.
7. **Traceability can be absent while “required.”**
   `hub_core/config_visual_outputs.py:92-106` checks completeness only when at
   least one traceability key was supplied; omitting all three bypasses it.
8. **Canonical document evidence is weak.** `hub_core/canonical_docs.py:9-28`
   checks `exists()` but not containment, regular-file status, or symlink escape.
9. **Generic CV warnings can mislabel numeric identifiers/time/concentration as
   noise.** `hub_core/data_contract_semantic_quality.py:25-37` scans every
   numeric column without a declared measurement role.

## 5. Target architecture

```text
LLM / coding agent
  - interprets data and user intent
  - writes project-local Python/R plotting scripts
  - chooses composition and aesthetics
  - inspects the rendered preview and revises
            |
            v
Thin default agent surface
  health / capabilities (bounded, on demand)
  inspect_data
  render_basic_csv
  render_project_script
  audit_artifact
            |
            v
FigOps kernel
  project/data path containment and symlink defense
  isolated snapshot execution and timeout
  declared input/output and artifact verification
  data contracts, units, statistical-claim evidence
  provenance and deterministic evidence envelopes
  objective geometry/contrast measurements
            |
            v
Explicit policy packs
  research-ops-v4
  publication-readiness-v2
  journal-{nature,science,acs,rsc,elsevier,wiley,cell}
  lab/project policy
            |
            v
Human review
  scientific validity / venue suitability / approval
```

Dependency direction remains the one in `docs/architecture.md`: MCP transport
and tools call lower-level services; lower-level services never import MCP.
Compatibility is an adapter layer, not duplicated kernel logic.

## 6. Target v2 agent surface

The names below are the target default conceptual surface. Final registry names
may be adjusted once for consistency before WP5 begins; after that, names and
schemas are frozen by witness tests.

### 6.1 `figops.inspect_data`

Read-only, bounded metadata inspection for an allowed data file.

Inputs:

- `data_path`;
- optional `columns` filter;
- optional `include_samples=false`;
- optional bounded `sample_rows` (maximum 20).

Default output:

- format, byte size, row/column counts;
- column name, inferred dtype, null count/fraction, finite range when numeric,
  bounded unique count/cardinality, and declared unit/role when available;
- truncation flags and warnings;
- input SHA-256.

Raw rows are not returned by default. Sampling is explicit, redacted/bounded,
and still subject to allowed-root, file-size, and cell-length limits.

### 6.2 `figops.render_basic_csv`

A small quick-chart lane, not the primary language for sophisticated figures.

Required inputs are `data_path`, `x`, and `y`. Optional inputs are limited to
`plot_type`, `series`, `facet`, `labels`, `style_policy`, `output_format`,
`job_id`, and `overwrite`. An `advanced` free-form object is not permitted.
Unsupported needs return a clear recommendation to use a project-local script.

Defaults preserve raw labels and authored data. A successful call performs
validation and render in one job, then returns artifact metadata, evidence, and
a preview resource URI. Dry-run is not part of this non-source-mutating lane.

### 6.3 `figops.render_project_script`

The primary lane for capable agents and complex figures.

- Accepts a project selector plus a configured figure/script selector.
- Executes only a project-local `.py` or `.R` script that is a regular,
  non-symlink file contained by the resolved project and declared in
  `project_config.yaml` visual outputs.
- Accepts no source-code string, command string, inline module, or arbitrary
  interpreter flags.
- Reuses project snapshotting, environment injection, timeout, output
  verification, data contracts, research-ops, and provenance.
- Returns the same evidence envelope and preview contract as basic rendering.

Writing or editing the project-local script is a normal workspace coding action
outside the MCP render payload and remains subject to user authorization.

### 6.4 `figops.audit_artifact`

Read-only synthesis for a completed job.

- Validates the evidence-envelope schema before evaluation.
- Applies the kernel integrity gates unconditionally.
- Applies zero or more explicit policy packs.
- Returns hard failures, advisory findings, informational measurements,
  unavailable/skipped evidence, provenance coverage, and the preview URI.
- Never returns `approved`, `publishable`, or equivalent.

### 6.5 Supporting discovery

`figops.health` stays. Capability/style/project discovery becomes concise and
filterable through `figops.describe` or resources and is fetched on demand, not
expanded into every rendering prompt. Project scaffolding/normalization and
batch operations remain available but outside the default figure-making tool
context.

## 7. Evidence and policy contracts

### 7.1 Evidence envelope v2

Every render path emits one deterministic `figops_evidence/2` envelope with:

- job/render kind and producer version;
- artifact entries with logical role, relative path, media type, byte size,
  dimensions/header validation, and SHA-256;
- failure stage and status with a closed enum;
- normalized data-contract and calculation-check summaries;
- input/config/script/environment/output provenance hashes;
- raw geometry measurements containing only metric ID, value, unit, scope, and
  availability/reason; raw evidence contains no severity or readiness outcome;
- label transformations and other authored-output mutations;
- one canonical `resolved_policy` snapshot when a policy is selected, with
  named/versioned projections referring back to that singular snapshot;
- baseline state only when a baseline policy was explicitly requested;
- explicit `unavailable` records for skipped/failed measurements.

Producer and consumer use one shared schema/enum module. Unknown schema versions,
missing mandatory producer fields, duplicate diagnostic IDs, and inconsistent
summary/detail state fail closed.

### 7.2 Policy projection and severity model

Severity and outcomes exist only in a named, versioned policy projection. The
projection cites raw metric IDs and declared contracts without rewriting the raw
measurement. A raw geometry producer must not emit `hard`, `advisory`,
`blocked`, `passed-policy`, or equivalent policy conclusions.

- **hard**: containment, corrupt/missing artifact, invalid dimensions/header,
  required provenance absence, declared contract/unit/range failure,
  unsupported statistical claim, or a minimum font/line failure only when the
  minimum comes from the selected explicit policy or a declared project
  contract.
- **advisory**: crowding, overlap, blank area, hierarchy consistency, legend
  placement, label proximity, baseline difference requiring interpretation.
- **informational**: density, exact visual difference values, skipped optional
  checks, timing and size metrics.
- **human**: scientific validity, final claim strength, accessibility tradeoff,
  and venue acceptance.

An aggregate status is computed from policy-selected gates, never from a flat
`all()` across every measurement.

### 7.3 Mutation policy

The default is `compliance_mode="validate"`:

- do not move artists;
- do not replace palettes;
- do not clamp font/line values;
- do not rewrite labels.

`compliance_mode="clamp"`, decluttering, CVD palette substitution, and legacy
label compression are explicit options/policy actions. Every applied mutation
records field/artist, before, after, reason, and policy ID in the evidence
envelope. Validation may recommend a change without applying it.

### 7.4 Resolved research-ops policy

This plan preserves the `AGENTS.md` contract. For `project.role: module`, Tier
1-3 research-ops remains enabled by default and is recorded in evidence as the
resolved policy `research-ops-v4`. Existing explicit `false` opt-outs remain
valid, scoped relaxations and are recorded with the resolved value and source.
Changing that default or removing an opt-out requires a separate migration
decision; it is not implied by making policy explicit in the agent surface.

### 7.5 Reproducibility hashes and visual baselines

Exact SHA-256 equality is informational evidence of exact-byte
reproducibility. A hash mismatch reports non-identity; by itself it does not
mean that a figure is visually worse or scientifically invalid.

A visual baseline may become advisory or gating only when all of the following
are present: a named/versioned pixel or perceptual-diff algorithm, an explicit
reference artifact, an explicit candidate artifact, compatible render
dimensions/color assumptions, and a selected policy with thresholds. The
evidence envelope keeps exact hashes and visual-diff results in separate fields.
Missing reference/candidate or algorithm metadata makes the visual comparison
unavailable, never silently passed.

## 8. Compatibility strategy

Compatibility is required for the existing independent CLI/runtime contract.

1. `orchestrator.py`, current CLI arguments, `project_config.yaml`, environment
   variables, and current project-local script execution continue to work.
2. Existing 14 `figops.*` tools and 13 frozen `graphhub.*` aliases remain
   callable during migration through compatibility handlers/adapters.
3. WP1-WP4 are additive or safe bug fixes; the existing MCP discovery surface
   remains default until the v2 surface passes the acceptance suite.
4. Before a lean default surface is enabled, the server gains an explicit
   surface selection (`v2` and `compatibility`) with a documented launcher/CLI
   setting. Compatibility mode exposes the full existing schema and routes to
   the same strengthened kernel.
5. Advanced legacy render fields keep their behavior in compatibility mode;
   they are not copied into `render_basic_csv`.
   Compatibility preserves payload shape and supported visual options only. It
   cannot bypass project-path containment, artifact verification, strict raw
   integrity, provenance requirements, or statistical-claim provenance. An
   unsupported significance marker is rejected or explicitly reported as
   unsupported in every profile, including legacy aliases.
6. Raw-preserving labels are a safety correction. Reproduction of previous
   output uses an explicit `legacy_compress` transform; compatibility adapters
   may inject it only when the selected compatibility contract promises legacy
   rendering semantics.
7. Existing manifest/status files remain readable. An adapter normalizes v1
   evidence into v2 with explicit `unavailable` fields; it must not invent
   hashes or pass states.
8. Deprecation requires two minor releases of warning, a migration example, and
   a runtime-witness test. No existing callable name is deleted in this plan.

Rollback does not revert security/integrity fixes. It switches MCP discovery
back to compatibility mode and disables v2 routing while both surfaces continue
to use the corrected kernel.

## 9. Work packages

Each work package should be one coherent branch/PR when practical. Agents must
update the checklist in section 16 and add the exact tests run.

### WP0 — Freeze baselines and add failing witnesses

Difficulty: high. Dependencies: none.

- Add minimal reproductions for all P0 defects before changing behavior.
- Capture canonical tool/schema size, property counts, and render call counts.
- Add a small agent-eval fixture set: simple CSV, complex project script,
  path-escape attempts, unsupported statistical annotation, failed artifact,
  missing provenance, and image-review revision.
- Do not bless current unsafe outcomes as expected behavior.
- Red-main is forbidden. A failing witness is kept as unmerged evidence, or as
  a narrowly scoped `xfail(strict=True)` with an owner and expiry, and becomes a
  normal passing test in the same PR as its fix. WP0 must never merge a broken
  full pytest suite.

### WP2-A — Freeze the evidence-envelope interface

Difficulty: highest/contract-sensitive. Dependencies: WP0.

- Freeze raw measurement, availability, artifact, provenance, resolved-policy,
  mutation-ledger, and policy-projection fields before WP1 implementation begins.
- Keep raw geometry facts severity-free; policy findings reference metric IDs.
- Assign file ownership so later packages do not concurrently edit the same
  evidence or geometry contracts.
- This is the interface subphase of WP2, not a separately shippable partial
  readiness implementation.

### WP1 — Unify project input containment

Difficulty: highest/security-sensitive. Dependencies: WP0 and WP2-A interface
freeze.

- Add one lower-layer contained project-input resolver.
- Apply it to config validation, data-contract collection/preflight/read,
  prefetch inputs, canonical-document path mechanics, provenance inputs, and
  project script/output selection where equivalent gaps exist.
- Reject absolute paths, traversal, escaping symlinks, non-regular required
  inputs, and time-of-check/time-of-use boundary changes.
- Keep MCP allowed-data-root handling separate from project-relative inputs.
- WP1 owns `project_paths`, config/data-contract integration, and canonical-doc
  containment/regular-file mechanics; it does not own readiness consumption.

### WP2 — Repair integrity and evidence/readiness semantics

Difficulty: highest/contract-sensitive. Dependencies: WP2-A and WP1.

- Implement the already-frozen producer/consumer evidence enums and envelope
  validation.
- Gate artifact failure, failure stage, provenance completeness, strict raw seal,
  and declared baseline state correctly.
- Accept producer-valid `warning`; distinguish unavailable/skipped from malformed.
- Fix traceability fail-open and consume WP1 canonical-document path evidence in
  readiness without duplicating path mechanics.
- Remove generic scientific meaning from undeclared numeric CV scanning.
- WP2 owns `evidence_contract`, artifact integrity, raw integrity, readiness, and
  canonical-doc evidence consumption; it does not own plotting/theme/geometry
  measurement implementation.

### WP3 — Preserve authored output and require claim provenance

Difficulty: high. Dependencies: WP2.

- Make raw labels the default and add explicit label mapping/legacy transform.
- Replace hidden style mutation with validate-by-default compliance and a
  mutation ledger.
- Remove invented statistical claims from examples.
- Require evidence IDs/hashes/test metadata for inferential annotations.
- Split objective diagnostics from hard/advisory policy outcomes.
- WP3 owns plotting, themes, raw geometry measurements, and statistical-claim
  linkage; it consumes the frozen envelope and does not edit readiness policy.

### WP4 — Expose bounded visual evidence

Difficulty: high/security-sensitive. Dependencies: WP1 and artifact schema from
WP2.

- Add contained job artifact/preview MCP resources with strict job ID, manifest
  membership, path containment, regular-file, media-type/header, and size checks.
- Generate a bounded preview for PDF/vector-only output without modifying the
  primary artifact, using the page/time/pixel/memory limits in section 13.
- Return preview URI from render and audit envelopes.
- Update agent workflow so the LLM inspects the image before targeted revision.

### WP5 — Implement thin v2 tools

Difficulty: highest/architecture-sensitive. Dependencies: WP1-WP4.

- Add bounded `inspect_data` service and tool.
- Add `render_basic_csv` as a compact adapter over existing rendering/kernel
  services.
- Add `render_project_script` over the existing declared project figure and
  snapshot runtime; never accept code/command strings.
- Add `audit_artifact` over v2 evidence plus explicit policy packs.
- Ensure one render call returns all artifact/evidence/preview references needed
  for the next reasoning step.
- Add MCP tool annotations that truthfully distinguish read-only
  inspect/audit from executing/writing render/apply operations.
- In writes-disabled mode, keep inspect/audit/preview reads available while
  render/apply fail closed.

### WP6 — Surface profiles and compatibility adapters

Difficulty: high. Dependencies: WP5.

- Add `v2` and `compatibility` registry/discovery profiles.
- Keep existing handlers and graphhub aliases callable.
- Move full legacy schema discovery out of the default v2 context only after
  acceptance thresholds pass.
- Generate separate default and compatibility tool references.
- Retain dry-run by default for source-mutating scaffold/normalize operations;
  remove mandatory dry-run choreography from non-source-mutating render prompts.
- Ensure `tools/list` annotations and exposed capabilities are truthful when MCP
  write tools are disabled; discovery must not advertise a write as available
  when dispatch will deny it.

### WP7 — Agent evaluations, docs, and release transition

Difficulty: medium-high. Dependencies: WP6.

- Run model-agnostic task evaluations against v2 and compatibility surfaces.
- Update `docs/architecture.md`, `docs/ROADMAP.md`, agent protocols, playbook,
  generated tool docs, `CHANGELOG.md`, and version metadata as required.
- Publish migration and rollback instructions.
- Do not claim v2 default readiness until every acceptance gate passes.

## 10. File-level change map

This is an ownership map, not permission to combine unrelated edits.

| Area/file | Intended change |
|---|---|
| `hub_core/project_paths.py`, `hub_core/project_config_reader.py` (new) | canonical contained project-input resolution plus verified, bounded config discovery/resource reads without pathname reopen |
| `hub_core/config_parser.py`, `hub_core/config_research_metadata.py`, `hub_core/config_visual_outputs.py` | WP1 path declarations and WP2 traceability completeness in separate commits/ownership windows |
| `hub_core/data_contract.py`, `hub_core/data_contract_io.py` | WP1 guarded prefetch/read; WP2 normalized evidence consumption after WP1 merges |
| `hub_core/canonical_docs.py` | WP1 containment/regular-file mechanics only; WP2 consumes its evidence through a stable result contract |
| `hub_core/raw_integrity.py`, `hub_core/provenance_inputs.py` | WP2 fail-closed integrity and provenance coverage, using WP1 path helper where needed |
| `hub_core/evidence_contract.py`, `hub_core/evidence_artifact_section.py`, `hub_core/evidence_semantics.py` (new) | WP2-owned envelope/status/availability, focused artifact section, singular `resolved_policy`, and cross-field semantic validation; raw metrics remain severity-free |
| `hub_core/artifact_integrity.py`, `hub_core/artifact_audit.py` (new) | verified-descriptor artifact facts and integrity-kernel/explicit-policy audit |
| `hub_core/publication_evidence.py`, `hub_core/publication_readiness.py`, `hub_core/publication_geometry_readiness.py` | consume v2 contract; gate decisive integrity evidence; keep geometry policy projection focused |
| `hub_core/data_inspection.py`, `hub_core/data_inspection_worker.py` (new) | bounded format-aware profile service and terminated worker with hashes and truncation |
| `plotting/bridge_renderer.py`, `plotting/renderers/labels.py`, `plotting/renderers/overlays.py`, `plotting/renderers/annotation_normalization.py`, `plotting/utils.py` | raw label default, explicit maps/transforms, mapping evidence, and focused overlay/annotation normalization |
| `themes/journal_theme.py`, `themes/compliance.py`, `themes/declutter.py` | validate-by-default; explicit mutation modes and ledger |
| `hub_core/geometry_diagnostics.py`, `hub_core/geometry_raw_contract.py`, `hub_core/geometry_style_checks.py` | WP3-owned raw metric ID/value/unit/availability only; minimum checks require a declared/selected policy |
| `hub_core/mcp/surface_profiles.py` (new) | lean/default and compatibility registry selection |
| `hub_core/mcp/schemas.py`, `hub_core/mcp/discovery_schemas.py` | v2 schemas, compatibility exposure, truthful read/write annotations and write-gated discovery |
| `hub_core/mcp/tools/data_tools.py` (new) | `inspect_data` handler |
| `hub_core/mcp/tools/render_v2.py` (new) | basic and project-script v2 orchestration adapters |
| `hub_core/mcp/tools/audit_tools.py` (new or extracted) | artifact audit/policy handler |
| `hub_core/mcp/resources.py`, `hub_core/mcp/manifest_io.py`, `hub_core/mcp/preview_artifacts.py`, `hub_core/mcp/preview_worker.py` | verified manifest/config resource reads, safe manifest-bound previews, lazy blobs, and bounded raster/PDF conversion |
| `hub_core/mcp/render_orchestration.py`, `hub_core/mcp/render_manifest.py`, `hub_core/mcp/render_response.py` | focused execution, immutable manifest, and compact one-render evidence/preview response |
| `hub_core/mcp/prompts.py`, `docs/internal/protocols/*` | evidence-first optional guidance; no forced render ceremony or image prohibition |
| `scripts/gen_tool_reference.py`, `docs/tools.md`, `docs/tools-v2.md`, `docs/tools-compatibility.md` | full maintenance, default-v2, and compatibility generated references with freshness checks |
| `tests/` | runtime witnesses, contract/schema budgets, compatibility, agent task evals |

Do not create new God Scripts. If a touched façade approaches the architecture
split signal, add a focused lower-layer module and preserve existing imports
through a compatibility shim.

## 11. Dependency graph and parallel execution

```text
WP0 baseline witnesses
        |
        v
WP2-A freeze evidence interface
        |
        v
WP1 containment/path mechanics
        |
        v
WP2-B evidence/integrity/readiness
        +--> WP3 authored output/raw geometry/claim linkage -+
        |                                                     +--> WP5 thin tools
        +--> WP4 preview resources ---------------------------+
                                                                 |
                                                                 v
                                                           WP6 profiles/adapters
                                                                 |
                                                                 v
                                                           WP7 eval/docs/release
```

Parallelism rules:

- WP2-A freezes the shared interface before WP1 starts. WP1 merges before WP2-B,
  and WP2-B merges before WP3; these safety-critical packages do not implement
  overlapping contracts in parallel.
- After WP2-B merges, WP3 and WP4 may run in parallel only when their file
  ownership is disjoint: WP3 owns plotting/themes/raw geometry/claim linkage;
  WP4 owns MCP resource/blob/rasterization code. Both must merge before WP5.
- Test fixture preparation and independent review may run in parallel, but no
  two agents edit `canonical_docs.py`, the evidence contract/readiness files, or
  geometry policy boundaries during the same ownership window.
- WP4 may start resource threat-model tests early but cannot merge before WP1
  containment and WP2 artifact membership are stable.
- WP5 is integration-heavy and must not invent alternate security/evidence
  helpers.
- Main-session responsibility is orchestration, conflict resolution, acceptance
  review, and checklist updates; implementation is delegated by package.

Suggested agent allocation by difficulty:

- highest-capability reasoning agents: WP1, WP2, WP5, WP6 architecture and
  security/compatibility review;
- strong implementation agents: WP3 and WP4;
- focused test/documentation agents: WP0 fixtures and WP7 docs/evals;
- independent reviewer agents: containment bypass, evidence consistency,
  schema/context budget, and compatibility regression audits.

## 12. Runtime-witness test plan

Unit tests alone are insufficient for behavioral changes. Each item below must
exercise the public or closest production path.

### 12.1 Boundary and integrity witnesses

- MCP project render rejects absolute `csv_checks[].path` outside the project.
- CLI and MCP project render reject `../` traversal and an internal symlink to
  an external data file.
- A contained regular input passes and is prefetched/read exactly once through
  the guarded path.
- Swapping a checked path to a symlink before read fails closed.
- Strict raw-integrity mode with no manifest blocks validation/render/readiness;
  warn mode reports warning and remains reviewable.
- Canonical doc must be a contained regular non-symlink file.

### 12.2 Artifact and readiness witnesses

- `artifact_status="failed"` or non-empty failure stage always blocks even when
  geometry/layout summaries say passed.
- Missing mandatory input/config/script/output hashes block the corresponding
  policy gate.
- Producer `warning` calculation status yields a supported advisory outcome,
  not `CALCULATION_STATUS_INVALID`.
- Optional skipped geometry is informational; skipped required clipping or
  integrity evidence blocks according to policy.
- Corrupt PNG/PDF header, zero dimensions, hash mismatch, and missing declared
  output block.
- Exact SHA equality/mismatch is reported separately from visual quality. A
  visual baseline affects policy only with versioned diff algorithm plus named
  reference and candidate artifacts; incomplete comparison is unavailable.
- Clean automatic evidence ends in `needs_review`, never approval.
- A module project with no explicit research-ops override resolves to
  `research-ops-v4`; each existing explicit `false` opt-out remains effective
  and is recorded in evidence.

### 12.3 Authored-output witnesses

- `ABC_DEF` renders byte-for-byte as `ABC_DEF` by default.
- Explicit mapping changes display text and records original/display mapping.
- Legacy compression reproduces the prior transformation only when requested.
- Validate mode makes no artist/font/line/palette/label mutation.
- Clamp/declutter mode records every before/after mutation.
- A significance marker without evidence ID/hash is rejected; a correctly
  linked calculation annotation renders and is traceable.

### 12.4 Visual and agent witnesses

- One successful render response includes usable artifact, manifest, evidence,
  and preview resource references without a follow-up collect call.
- Preview resource rejects unknown job IDs, paths absent from manifest,
  traversal, symlink, MIME/header mismatch, and oversize files.
- Preview bytes are fetched only when the resource is read, not embedded in the
  render/audit text response. The resource returns an MCP `blob` only for the
  preview MIME allowlist (`image/png`, `image/jpeg`, `image/webp`) after magic
  validation; tests enforce raw and base64-encoded size limits.
- PDF/vector preview generation rejects extra pages, excessive pixel area,
  timeout, memory limit, malformed content, and decompression-expansion limit.
- `inspect_data` rejects or truncates at its input-byte, scan-row,
  decompressed-byte, wall-time, and memory limits with explicit availability
  reasons; compressed/container bomb fixtures cannot exhaust the process.
- An agent can inspect a CSV without prior knowledge of columns, choose a valid
  plot, render it in one call, view the image, and make a targeted second render.
- A complex figure is authored as a project-local declared script and rendered
  without any code string in the MCP payload.
- Existing CLI project render and compatibility MCP render produce valid
  artifacts through the strengthened kernel.

### 12.5 MCP capability and write-gating witnesses

- Tool annotations identify inspect/audit as read-only and render/apply as
  executing or mutating; annotations match live dispatch behavior.
- With `GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED` unset/false, `inspect_data`,
  `audit_artifact`, and manifest/preview resource reads succeed, while all
  render/apply tools fail closed before creating a job or source artifact.
- `tools/list` under writes-disabled configuration either omits unavailable
  writes or marks them unavailable with truthful annotations; it never claims a
  denied operation is enabled.
- The same witnesses run against v2 and compatibility profiles, proving legacy
  aliases cannot bypass write gating or P0 safety fixes.

## 13. Schema, context, and response budgets

Budgets are acceptance gates, not aspirations.

| Budget | Target |
|---|---:|
| Default v2 canonical figure-making tools exposed at once | <= 7 |
| Compact JSON for default `tools/list` definitions | <= 24 KiB |
| Any single default tool input schema | <= 6 KiB |
| `render_basic_csv` top-level input properties | <= 14 |
| Default `inspect_data` response | <= 32 KiB |
| Default audit/evidence text response | <= 64 KiB |
| Sample rows | default 0, explicit maximum 20 |
| Returned columns | maximum 256 with truncation marker |
| Returned cell/string length | maximum 512 characters with truncation marker |
| Inspect source file | default maximum 64 MiB |
| Inspect decoded/decompressed bytes | maximum 256 MiB and expansion ratio 20x |
| Inspect scan | maximum 1,000,000 rows or 10 seconds, whichever occurs first |
| Inspect worker memory | maximum 256 MiB attributable working-set increase |
| Inspect SHA-256 read | same 64 MiB source cap, 1 MiB streaming chunks, shared 10-second deadline |
| Preview image before base64 | maximum 2 MiB and 2,048 px on longest edge |
| Preview base64 payload | maximum 2,796,204 bytes for a 2 MiB raw blob |
| PDF/vector preview | PDF first page only; 5-second timeout, maximum 8 MP and 256 MiB worker memory; safe SVG is explicitly unavailable until a Windows renderer smoke passes |
| Simple CSV task | one inspect + one render; no mandatory collect/dry-run |
| Known-schema CSV task | one render call |
| Project script render | one render call after the script/config exists |

Compatibility schemas and generated full references are excluded from the
default-context budget but remain available on demand. Tests serialize the live
JSON-RPC `tools/list` result, not a hand-counted proxy. Budget changes require a
recorded architecture decision in section 17.

Inspection and preview conversion run in bounded workers where hard memory/time
termination can be enforced. Formats whose decoded size cannot be established
safely within the limits return `unavailable` and a resolution hint; they do not
fall back to an unbounded full read. Render/audit responses carry only preview
metadata and URI. Blob/base64 content is produced on demand after MIME magic and
manifest membership checks, and both pre-encoding and post-encoding sizes are
validated.

The inspect byte limit is configured through a new validated runtime knob,
`GRAPH_HUB_MCP_INSPECT_MAX_BYTES`, with a 64 MiB default and a 256 MiB absolute
ceiling; operators may reduce it but cannot widen it beyond the ceiling. Invalid
or non-positive values use the default with a health warning. The same resolved
cap applies before parsing and before/hash streaming, so hashing cannot become
an unbounded second read. Decompression/decoded-byte, row, deadline, and worker
memory caps remain fixed kernel ceilings. Preview blobs use fixed limits and do
not accept a request override. PDF conversion reads page 1 only and runs in a
terminated worker under the 5-second, 8 MP, and 256 MiB limits. The attempted
CairoSVG dependency path was rolled back because no SVG renderer passed the
required Windows safety smoke. Sanitized SVG input therefore returns typed
`SVG_RENDERER_UNAVAILABLE`; source SVG bytes are never returned as a preview.

### 13.1 Final live v2 measurement (2026-07-15)

`tests/fixtures/ai_native_agent_eval/baseline-v1.json` remains the immutable
pre-patch measurement. `final-v2.json` records the post-patch working tree and
is checked against live JSON-RPC discovery and generated files.

| Measurement | Baseline v1 | Default v2 |
|---|---:|---:|
| Discovered tools with writes enabled | 14 | 7 |
| Compact `tools` array | 51,455 B | 9,592 B |
| JSON-RPC `tools/list` response | -- | 9,636 B |
| Largest input schema | 9,682 B | 987 B |
| Basic CSV top-level properties | 46 | 11 |
| Known-schema render calls | 2 | 1 |
| Follow-up collect calls | 1 | 0 |
| Default-surface generated reference | 129,241 B | 15,257 B / 880 lines |

This is an 81.4% reduction in the default tool-definition context, an 89.8%
reduction in the largest input schema, and an 88.2% reduction in the generated
default-surface reference. With writes disabled, discovery contains five
read-only tools in a 6,317-byte compact array and a 6,361-byte JSON-RPC
response. The on-demand compatibility reference is 133,404 bytes and 5,815
lines (8.7x the default-v2 bytes and 6.6x its lines); the all-canonical
maintenance reference is 158,253 bytes and 7,425 lines (10.4x the default-v2
bytes and 8.4x its lines) and is not a default prompt/discovery payload.

The focused documentation, architecture, profile, agent-consumability,
baseline/evaluation, and visual-protocol gate passed 46 tests on 2026-07-15;
targeted Ruff and `git diff --check` also passed.

The live model witness in `live-preview-revision-v1.json` used an actual v2
server for two renders, two lazy preview reads, and zero collect calls. Visual
inspection found a row-order zigzag, missing title/legend, and raw underscore
labels. The only revision added the `Scenario` series and authored title/axis
labels; it added no statistic, aggregate, interval, or significance claim. The
second preview visually confirmed separate monotonic series, a legend, and the
authored labels. Response/evidence/manifest/resource hashes agreed, the initial
primary artifact remained immutable, preview bounds held, temporary fixture and
runtime jobs were removed, and no human or publication approval was claimed.

The definitive automated release gate completed in 254.54 seconds with 2,005
tests passed, 45 skipped, 99 subtests passed, 28 warnings, and zero failures.
Full Ruff and `git diff --check` passed; the final architecture/docs/profile/
schema-budget gate passed 30 of 30 tests; and the independent final quality
review approved the patch with zero blockers. `Rscript` was absent on this host,
so real-R execution remains an explicit environment limitation rather than an
inferred success.

## 14. Acceptance criteria

The rearchitecture is complete only when all criteria pass.

### Safety and correctness

- Zero successful project-input escapes across absolute, traversal, symlink,
  junction/reparse-point where applicable, and TOCTOU witness cases.
- Every render has verified declared outputs and required provenance coverage.
- Strict integrity and missing/corrupt artifact cases fail closed.
- Unsupported statistical claims cannot be rendered as supported claims.
- Raw labels are preserved by default; every mutation is explicit and logged.
- Raw geometry evidence contains no severity/outcome; every finding cites a
  selected policy and raw metric ID. Font/line minimum failures require an
  explicit selected policy or declared contract.
- Exact-byte hashes and versioned reference/candidate visual differences remain
  distinct evidence and cannot be substituted for one another.
- Module projects still resolve Tier 1-3 defaults to `research-ops-v4`, with
  existing explicit `false` opt-outs preserved and evidenced.

### Agent capability

- The agent can inspect bounded data facts without already knowing column names.
- The agent can use project-local Python/R code for complex figures without
  encoding code in tool arguments.
- The agent receives and can inspect a preview after render.
- Hard diagnostics guide correction without preventing aesthetic reasoning.
- Simple and project render call-count targets in section 13 pass.

### Contract and compatibility

- Existing CLI commands and project configs pass regression tests.
- All current `figops.*` and frozen `graphhub.*` tool names remain callable in
  compatibility mode.
- Every profile, including compatibility aliases, enforces containment,
  artifact/raw-integrity, write-gating, and statistical-claim provenance.
- V1 manifests normalize honestly; absent v2 evidence is marked unavailable.
- `docs/tools.md`/profile references are generated from live registries and
  freshness-tested.
- Default surface and response budgets pass on Windows and CI-supported POSIX.
- Writes-disabled discovery/annotations match dispatch: inspect/audit/preview
  remain readable and render/apply remain unavailable without side effects.

### Quality

- `python hub_uv.py run python -m pytest` passes.
- `python hub_uv.py run ruff check .` passes.
- Every behavioral change has a runtime witness.
- Agent-eval fixtures record completion, calls, hard-error catch rate,
  provenance rate, and preview-driven revision success.

## 15. Migration and rollback

### Migration sequence

1. Land witnesses and P0 kernel fixes while the current surface remains default;
   no PR merges failing tests except a strict, owned, expiring `xfail` that is
   converted to passing with its fix.
2. Land v2 evidence and preview additively; let current render tools emit them.
3. Land thin v2 tools and run side-by-side evaluations.
4. Add explicit surface selection and document launcher configuration.
5. Switch the default to v2 only after all acceptance criteria pass.
6. Maintain compatibility callability and warnings for at least two minor
   releases; removal is outside this plan.

### Operator/user migration

- Existing CLI users require no immediate change.
- Existing MCP clients may select compatibility mode and keep current payloads.
- New clients use data inspection, basic render, or declared project-script
  render and consume the unified evidence/preview response.
- Projects that relied on implicit label compression or save-time clamps add an
  explicit compatibility transform/policy to reproduce the old visual.
- Projects using inferential annotations add calculation evidence references.
- Module projects retain the existing resolved `research-ops-v4` default and
  explicit false opt-outs; any default-policy change uses a separate migration.

### Rollback triggers

- material CLI/project-config regression;
- default tool schema/context budget regression;
- preview resource boundary defect;
- evidence v2 false pass on a hard integrity failure;
- compatibility handler cannot reproduce a supported existing payload.

### Rollback action

Switch default discovery/routing to compatibility mode, preserve v2 artifacts
for diagnosis, and revert only the affected v2 adapter. Do not revert project
path containment, artifact verification, strict integrity, or unsupported-claim
blocking. Record trigger, affected release/commit, and recovery owner in section
17.

## 16. Execution checklist

Later agents update `[ ]` to `[x]` only with linked code/tests in the note.
Use `[~]` for in progress and `[!]` for blocked.

### WP0 — baseline

- [x] No failing witness merged to main; each defect witness is green with its
      fix or a strict, owned, expiring `xfail`.
- [x] P0 path-escape runtime witnesses added.
- [x] Label mutation witness added.
- [x] Failed-artifact/provenance and warning-status readiness witnesses added.
- [x] Strict-unsealed raw-integrity witness added.
- [x] Unsupported statistical annotation witness added.
- [x] Agent-eval fixtures and baseline measurements recorded in immutable
      `baseline-v1.json`; the live post-patch measurement is `final-v2.json`.

### WP1 — containment

- [x] WP2-A evidence-envelope interface frozen before WP1 implementation.
- [x] Shared contained project-input resolver implemented.
- [x] Config, data-contract, prefetch/read, canonical-doc path mechanics,
      provenance, and script/output paths routed through it where applicable.
- [x] Absolute/traversal/symlink/TOCTOU witnesses pass on supported platforms.
- [x] Independent boundary audit completed.

### WP2 — evidence and integrity

- [x] Shared evidence/status contract implemented.
- [x] Raw geometry contract contains metric/value/unit/availability only;
      severity/outcome exists only in selected policy projections.
- [x] Artifact/failure/provenance gates fixed.
- [x] Calculation `warning` and unavailable/skipped semantics aligned.
- [x] Strict raw integrity fails closed.
- [x] Traceability and canonical-doc fail-open gaps fixed.
- [x] `research-ops-v4` module default and explicit false opt-outs resolve into
      evidence without changing current behavior.
- [x] Exact SHA and versioned reference/candidate visual-diff evidence are
      separate and correctly projected.
- [x] Evidence v1 adapter and v2 validation witnesses pass. The canonical field
      name is the singular `resolved_policy`.

### WP3 — authored output and claims

- [x] Raw-preserving labels are default and mappings are recorded.
- [x] Hidden palette/clamp/declutter changes removed from validate mode.
- [x] Mutation ledger implemented for explicit transformation modes.
- [x] Statistical examples no longer invent claims.
- [x] Inferential annotations require calculation evidence.
- [x] Geometry measurement and policy severity are separated.

### WP4 — previews

- [x] Safe preview/artifact resource implemented.
- [x] Preview generated/returned for raster and PDF-primary jobs; safe SVG is a
      typed unavailable result until a renderer passes the Windows safety smoke.
- [x] Resource containment, manifest-membership, MIME/header, and size witnesses
      pass.
- [x] On-demand blob, raw/base64 size, PDF first-page, SVG fail-closed,
      rasterization
      timeout/pixel/memory, and malformed/decompression witnesses pass.
- [x] Agent protocol permits and requires visual inspection before revision.

### WP5 — thin tools

- [x] `inspect_data` implemented with bounds/truncation/hashes.
- [x] Inspect input/hash byte, decoded/decompression, row, timeout, memory, and
      expansion-ratio witnesses pass.
- [x] `render_basic_csv` implemented within schema budget.
- [x] `render_project_script` implemented without code/command strings. Python
      and mocked-R dispatch pass; this host has no `Rscript`, so a real R render
      is recorded as an environment limitation rather than silently passed.
- [x] `audit_artifact` implemented with explicit policy packs.
- [x] Unified one-render response contract passes runtime witnesses.
- [x] Read-only/executing MCP annotations match writes-disabled dispatch.

### WP6 — compatibility and surface

- [x] V2 and compatibility surface profiles implemented.
- [x] Existing 14 canonical and 13 frozen alias tools callable in compatibility
      mode.
- [x] Default tools/list and per-tool schema budgets pass: 7 tools, 9,592-byte
      compact array, 9,636-byte JSON-RPC response, and a 987-byte largest input
      schema.
- [x] Generated docs are profile-aware and freshness-tested.
- [x] Mandatory dry-run/collect choreography removed from render guidance.
- [x] Writes-disabled `tools/list` is truthful; inspect/audit/preview reads pass,
      render/apply and compatibility aliases fail closed without side effects.

### WP7 — ship readiness

- [x] Full automated gate recorded: 2,005 passed, 45 skipped, 99 subtests
      passed, 28 warnings, zero failures in 254.54 seconds; full Ruff and
      `git diff --check` passed; architecture/docs/profile/schema budgets passed
      30 of 30 tests.
- [x] Simple CSV, known-schema CSV, project-script, and live visual-revision
      evals pass. The live v2 witness used 2 renders, 2 lazy preview reads, and
      0 collect calls; changed only series/authored labels; confirmed the second
      preview visually; preserved SHA consistency and initial-primary
      immutability; cleaned temporary state; and claimed no human approval.
- [x] `docs/architecture.md`, `docs/ROADMAP.md`, protocol/playbook, and generated
      references reflect the implemented working-tree state. Release changelog
      and version metadata remain part of the explicit release transition.
- [x] Migration and rollback instructions validated by compatibility/profile
      smoke tests.
- [x] Final fix sweep routes config and runtime-manifest consumers through
      strict unique resolution and verified descriptors (45 passed, 2 skipped
      in the focused integration gate); preserves verified PDF/SVG bytes and
      hashes while
      reporting unavailable vector dimensions explicitly; preserves raw-
      integrity availability/status without inventing pass state; and extracts
      evidence-artifact and annotation-normalization helpers so every module in
      the tracked architecture roots remains below the 800-line split signal.
- [x] Independent final security, evidence, agent-consumability, compatibility,
      and quality review completed with zero blockers.

## 17. Decision and execution log

Append entries; do not rewrite history.

| Date | Work package | Decision/evidence | Owner | Status |
|---|---|---|---|---|
| 2026-07-14 | Plan | Adopted “catch what the LLM misses without reducing LLM capability” as the governing architecture principle; current source evidence captured in sections 3-4. | Research Hub Commander | accepted |
| 2026-07-15 | WP0-WP2 | Closed the baseline P0 witnesses with one contained path kernel, strict raw/artifact/provenance evidence, and the validated `figops_evidence/2` contract. | Delegated implementation and independent reviewers | complete |
| 2026-07-15 | WP3-WP4 | Preserved authored labels/styles by default, required claim provenance, separated raw geometry from policy, and added manifest-bound bounded preview resources. SVG remains explicitly unavailable pending a safe Windows renderer. | Delegated implementation and independent reviewers | complete |
| 2026-07-15 | WP5-WP6 | Added four thin v2 capabilities, one-render evidence/preview responses, truthful annotations/write gating, default v2 discovery, and frozen compatibility discovery. | Delegated implementation and independent reviewers | complete |
| 2026-07-15 | WP7 | Generated full, v2, and compatibility references from live registries; captured `final-v2.json` without rewriting the v1 baseline. Final full-suite and independent release review remain release-orchestrator gates. | Documentation/evaluation owner | in progress |
| 2026-07-15 | WP7 fix sweep | Added verified config/manifest reads, honest PDF/vector dimension and raw-integrity availability, and final evidence/overlay module splits; full regression and final independent review remain open gates. | Delegated fix owners and documentation owner | complete |
| 2026-07-15 | WP7 final gate | Full pytest passed with 2,005 passed, 45 skipped, 99 subtests, 28 warnings, and zero failures in 254.54 seconds; full Ruff, diff check, 30/30 architecture/docs/profile/schema-budget tests, and independent quality review passed with zero blockers. Live model preview-revision evidence remains pending. | Release verification and independent quality reviewers | automated gates complete |
| 2026-07-15 | WP7 live model witness | An actual v2 server completed two renders and two lazy preview reads with zero collect calls; a targeted series/label-only revision removed the observed zigzag and added authored context without statistics, while hashes, primary immutability, bounds, cleanup, and non-approval boundaries held. | Live model evaluation owner | complete |

## 18. Explicit non-goals

- Building a general arbitrary-code execution API or accepting Python/R/command
  strings in MCP payloads.
- Replacing capable LLM visual reasoning with a deterministic aesthetic scorer.
- Automatic scientific approval, authorship judgment, publisher acceptance, or
  removal of human review.
- Guaranteeing current publisher requirements beyond explicit, versioned policy
  evidence.
- Rewriting the orchestrator, project config system, renderer, or themes from
  scratch.
- Removing existing CLI commands, environment contracts, project-local scripts,
  or legacy MCP aliases during this plan.
- Turning every aesthetic preference into a schema property.
- Returning unbounded raw datasets, PDFs, images, manifests, or diagnostic text
  in the LLM context.
- Adding DVC as a required runtime dependency.
- Introducing a third-party render backend SPI without a concrete consumer.

## 19. Definition of done

FigOps v2 is done when a capable LLM can freely inspect bounded data facts,
author and run a contained project-local figure, see the result, and revise it;
when FigOps reliably catches boundary, integrity, provenance, contract, and
unsupported-claim failures; when aesthetic policy is explicit and mutations are
observable; and when existing CLI/runtime users retain a tested compatibility
path.
