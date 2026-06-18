# Graph Hub Independent Completion Spec

- Status: Direction lock and implementation specification
- Date: 2026-06-08
- Scope: independent `graph-making-hub` repository, Graph Hub MCP, project graph contracts, HKS/common agent protocols
- Decision: Graph Hub is the primary graph and scientific figure system. Athena is optional and should not be required for graph routing. Use Athena or another toolbox only when a separate non-graph solver/literature/research step is explicitly needed.

## Executive Decision

Graph Hub should be completed as a narrow, high-quality specialist system:

```text
Agent / Server / Human
        |
        | explicit graph request
        v
Graph Hub MCP
        |
        v
Graph Hub Core
  - project and data contract
  - graph-specific calculation checks
  - central style system
  - render and quality gates
  - provenance and runtime contract
  - HKS/common protocol documents
        |
        v
validated figure + manifest + status + provenance
```

Athena remains a client, not the owner. It may call Graph Hub only for explicit legacy compatibility or mixed workflows where Athena produced non-graph data first, but Graph Hub must be fully usable without Athena.

## What Athena No Longer Owns

Athena should not own:

- graph style contracts,
- project graph folder structure,
- data contract validation,
- graph-specific statistical checks,
- figure rendering,
- visual preflight,
- artifact manifests,
- Graph Hub MCP schemas.

Athena may still own:

- natural-language routing,
- cross-tool orchestration,
- solver/literature/context workflows when the user asks for them,
- optional compatibility adapters during migration.

## Completion Pillars

### 1. Project And Data Contract

Graph Hub must treat data and config as the API.

Required surfaces:

- `project_config.yaml` is the project-level contract.
- Standard folders are `raw/`, `work/`, `hub_scripts/`, `results/data/`, `results/figures/`, `results/final/`, `docs/`, and `archive/`.
- `data_contract.csv_checks` validates input tables before rendering.
- `visual_style` and `presets` select Graph Hub style definitions without redefining them per project.
- Invalid configs are visible to agents instead of silently skipped.

Current source files:

- `project_config_template.yaml`
- `hub_core/config_parser.py`
- `hub_core/data_contract.py`
- `hub_core/project_discovery.py`
- `hub_core/project_normalization.py`

Done means:

- every active graph project can be discovered,
- every valid project has a `project_config.yaml`,
- invalid projects return specific config/data/style errors,
- no graph render runs from an unvalidated project unless explicitly marked as exploratory.

### 2. Graph-Specific Calculation Checks

Calculation checks that determine whether a figure is scientifically valid belong in Graph Hub.

Required checks:

- required columns,
- dtype checks,
- unit compatibility,
- value range,
- null allowance,
- uniqueness,
- monotonicity where declared,
- minimum row count,
- replicate count,
- grouped CV,
- mean/std/SEM/error-bar inputs,
- regression fit metadata,
- slope/intercept/R²/confidence interval metadata,
- outlier and anomaly flags,
- log-scale validity.

Non-goal:

- Graph Hub does not become a general physics/math solver. Domain derivations and literature reasoning can stay in markdown protocols or agent reasoning. Graph Hub only verifies calculations that are inputs to graphs or figure quality.

Current source files:

- `hub_core/data_contract.py`
- `hub_core/visual_regression.py`
- `plotting/utils.py`
- `project_config_template.yaml`

Done means:

- calculation checks are declared in config or HKS/common protocol files,
- failed checks block publication render or set `manual_review_needed=true`,
- outputs record the calculation status in `manifest.json` and `status.json`,
- agents can inspect calculation failures without reading raw data into chat context.

### 3. Central Style System

Graph Hub owns the style library.

Required style contract:

- `target_format`: `nature`, `nature_surfur`, `science`, `ppt`, `default`, `acs`, `rsc`, `elsevier`, `wiley`, `cell`
- `profile`: `baseline` plus validated profile aliases from `themes/style_profiles.py`
- `font_scale`
- `output_format`: `png`, `pdf`, `svg`
- optional `presets` for named project-level bundles.

Current source files:

- `themes/journal_theme.py`
- `themes/style_profiles.py`
- `plotting/bridge_renderer.py`
- `hub_core/config_parser.py`
- `project_config_template.yaml`

Done means:

- styles are defined centrally,
- projects only select or override styles through config,
- MCP style tools expose the same style set as Graph Hub core,
- `nature_surfur` is first-class,
- style drift between CLI, MCP, and agent docs is tested.

### 4. Render And Quality Gates

Graph Hub render must produce publication-style figures through controlled paths.

Required behavior:

- `graphhub.render_csv_graph` renders structured CSV jobs under the external runtime root.
- `graphhub.collect_artifacts` returns artifact metadata after render.
- render jobs do not write into source project trees unless an explicit apply/project tool is used.
- visual preflight reports pass/warning/failure.
- baseline comparison records matched/unmatched status.
- failed render stays a structured tool result, not an ambiguous protocol failure.

Current source files:

- `graphhub_mcp_server.py`
- `hub_core/mcp_surface.py`
- `plotting/bridge_renderer.py`
- `hub_core/figure_preflight.py`
- `tests/test_mcp_rendering.py`
- `tests/test_mcp_batch_quality.py`

Done means:

- output formats are generated correctly,
- `manual_review_needed` is set when quality is uncertain,
- render artifacts include `manifest.json`, `status.json`, and latest alias,
- `failure_stage` and `resolution_hint` are present,
- generated paths stay under the runtime root by default.

### 5. Provenance And Operating Contract

Graph Hub must make every result inspectable and reproducible.

Required fields:

- `job_id`
- `operation_id`
- `status`
- `failure_stage`
- `resolution_hint`
- `created_paths`
- `modified_paths`
- `skipped_paths`
- `artifact_resources`
- `manual_review_needed`
- `style_summary`
- `visual_preflight_status`
- `baseline_comparison`
- `manifest_path`
- `status_path`
- `latest_alias`

Current source files:

- `hub_core/mcp_surface.py`
- `hub_core/runtime_paths.py`
- `hub_core/provenance.py`
- `tests/test_runtime_paths.py`
- `tests/test_mcp_rendering.py`

Done means:

- every write-capable MCP result has a stable envelope,
- artifact metadata survives server restart,
- absolute path leakage is sanitized in diagnostics,
- protocol errors and execution errors are distinguishable,
- runtime state never creates source-tree `.venv`, `.r_libs`, DVC state, or long-lived caches.

### 6. Agent Usability

Graph Hub must be directly usable by agents without Athena.

Required MCP workflows:

```text
graphhub.list_styles
graphhub.list_projects
graphhub.inspect_project
graphhub.validate_project
graphhub.render_csv_graph
graphhub.collect_artifacts
graphhub.scaffold_project
graphhub.normalize_project_structure
graphhub.batch_check
```

Required agent guidance:

- use `list_styles` before assuming a style,
- use `inspect_project` and `validate_project` before project render,
- use `render_csv_graph` for explicit structured CSV render,
- use `collect_artifacts` after render,
- use `batch_check` for review boards, not passive health checks,
- do not call Athena for graph routing; use it only when a separate non-graph solver/literature step is actually needed.

Done means:

- every tool has input and output schema,
- every tool returns structuredContent,
- every tool documents dry-run/write behavior,
- failures give next-action hints that an agent can follow.

### 7. Project Migration And Scaffolding

Graph Hub must convert scattered graph projects into standard Graph Hub projects.

Required behavior:

- detect project folders,
- detect missing or legacy config paths,
- propose normalized folder layout,
- scaffold missing `project_config.yaml`,
- preserve raw data,
- avoid destructive moves unless explicit apply is requested,
- write manifests for modifications.

Current source files:

- `hub_core/project_discovery.py`
- `hub_core/project_normalization.py`
- `tests/test_mcp_normalization.py`

Done means:

- normalize tools can run dry-run first,
- apply mode is explicit,
- every created/modified/skipped file is recorded,
- existing graph projects can be migrated without Athena.

### 8. Real Acceptance Tests

Graph Hub is not complete until real workflows pass.

Required acceptance fixtures:

- a tiny CSV fixture for deterministic MCP render,
- one real research project using `nature_surfur`,
- one invalid project config that stays visible,
- one project normalization dry-run,
- one MCP direct-call workflow from server environment,
- one batch quality check.

Required commands:

```bash
python hub_uv.py run --with ruff python -m ruff check hub_core tests
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py tests/test_mcp_rendering.py tests/test_mcp_normalization.py tests/test_mcp_batch_quality.py -q
```

Done means:

- tests pass locally,
- MCP direct-call fixture passes from the server,
- generated artifacts can be inspected without Athena,
- acceptance does not depend on hidden chat context.

## HKS/Common Protocol

HKS is the common knowledge layer that agents read before using Graph Hub. If the project later gives HKS a different formal name, this section should be renamed without changing the contract.

HKS/common must contain:

- graph project folder standard,
- `project_config.yaml` schema guidance,
- style selection rules,
- calculation check vocabulary,
- unit and axis labeling rules,
- error-bar and replicate rules,
- regression/fitting reporting rules,
- visual review checklist,
- MCP tool workflow examples,
- failure-stage handling rules.

HKS/common must not contain:

- hidden one-off decisions only stored in chat,
- Athena-only style enums,
- raw data dumps,
- generated binary artifacts,
- vague instructions such as subjective beautification requests or unspecified validation requests.

Recommended file layout:

```text
docs/hks/
  00_agent_graph_workflow.md
  01_project_config_contract.md
  02_style_contract.md
  03_calculation_check_contract.md
  04_quality_gate_contract.md
  05_mcp_tool_playbook.md
```

Done means:

- agents can answer "which tool should I call next?" from HKS/common docs,
- graph-specific calculation checks have stable names,
- HKS docs and MCP schemas do not contradict each other,
- HKS docs are versioned in the Graph Hub repo.

## Roadmap

### Phase A: Contract Freeze

- freeze this spec as the Graph Hub completion direction,
- update the MCP surface index to point to this spec,
- create `docs/hks/` common protocol files,
- add tests that fail when style lists drift.

### Phase B: Calculation Check Expansion

- extend `data_contract.csv_checks` with named check vocabulary,
- add monotonicity, replicate count, grouped CV, and log-scale checks,
- record calculation-check status in manifests,
- add focused tests for every check.

### Phase C: Agent-First MCP Playbook

- write tool playbook examples,
- add direct MCP smoke fixture,
- document the exact direct-call workflow for servers,
- keep Athena adapter optional.

### Phase D: Project Migration

- run discovery on active project roots,
- classify valid/invalid/migratable projects,
- dry-run normalization,
- apply only after manifest review.

### Phase E: Publication Figure Hardening

- add real-project acceptance test,
- add visual review board,
- add baseline comparison examples,
- add manuscript figure pack workflow only after single-figure reliability is stable.

## Open Risk Review

The former promotion blocker was the lack of a project-aware MCP render tool.
The current target implementation adds `graphhub.render_project_figure` so
configured `project_config.yaml` figures can render under
`runtime_root/mcp_project_jobs/<job_id>/project` with the same
manifest/status/provenance/failure-stage envelope as `graphhub.render_csv_graph`.

Remaining acceptance risk:

- keep source-project writes out of the default path,
- add R-script parity only after the Python project-render contract is stable.

Local acceptance evidence, 2026-06-08:

- valid `nature_surfur` project render passed for `PI_control` / `FigPI_CvS_Fits`;
- render wrote under `~/Library/Caches/Graph_making_hub/mcp_project_jobs/real-pi-control-acceptance-20260608`;
- source project file snapshot was unchanged before/after render;
- snapshot contained no copied `raw/` files;
- `collect_artifacts` returned `renderer_surface=graphhub.render_project_figure`;
- stdio JSON-RPC direct-call to `graphhub_mcp_server.py` returned `status=ok` in dry-run mode;
- invalid `nature_surfur` project stopped at `failure_stage=CONFIG` without creating a job root;
- after artifact-based font preflight, the valid render returned `status=ok` and `manual_review_needed=false`.

Server acceptance evidence, 2026-06-08:

- server clone fast-forwarded to `2c4d198`;
- server smoke returned `status=ok`;
- server focused MCP/preflight suites passed;
- server ruff check passed;
- server stdio JSON-RPC direct-call returned `status=ok` in dry-run mode;
- server fixture project render and `collect_artifacts` returned `renderer_surface=graphhub.render_project_figure`;
- server Codex config and shared `agent-config` host config both register `mcp_servers.graphhub`;
- `codex mcp list` reports `graphhub ... enabled`;
- `codex doctor --summary` reports 0 fail.

These risks must also be tracked during implementation:

1. **HKS naming risk:** HKS is not defined in the current repo. This spec defines it as the common agent protocol layer. Rename if the intended meaning differs.
2. **Calculation scope risk:** Graph Hub should own graph-related checks, not general scientific derivation. Keep physics/math derivations in HKS methodology docs unless they directly affect figure validation.
3. **Adapter creep risk:** raw instrument adapters can easily become a second analysis engine. Only add adapter families with explicit input signatures, output schema, tests, and failure modes.
4. **Athena dependency risk:** new Graph Hub behavior must not import Athena or require Athena runtime.
5. **Visual quality risk:** numeric checks cannot prove publication readiness alone. Manual-review state must stay visible until visual preflight and baseline comparison pass.
6. **Project migration risk:** normalization must be dry-run first and manifest-backed; source raw data should never move silently.
7. **Server reproducibility risk:** repeat direct MCP acceptance after future server environment changes.

## Final Direction

Graph Hub should be finished as an independent scientific figure engine.

The default real workflow should be:

```text
read HKS/common protocol
inspect or scaffold project
validate project/data/style/calculation checks
render through Graph Hub MCP
collect artifacts
review manifest/status/preflight/provenance
```

Athena is optional. Use it only when the request genuinely needs a separate non-graph solver, literature, or local knowledge-base step beyond Graph Hub's graph contract.
