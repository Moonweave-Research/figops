# Post-Release Total QA and Next Plan

Review date: 2026-07-04

Source state: `0.17.11` after PyPI publication, `v0.17.11` GitHub Release, and
latest `main` CI success.

## Objective

Record the post-release re-check across three risk surfaces:

1. Whether journal tracks are implemented as meaningfully different graph style
   tracks, not only labels.
2. Whether agents can discover and use the complete FigOps MCP tool surface.
3. Whether operational release, QA, environment, and backlog controls are
   documented in the next plan.

This is a planning and evidence document. It does not promote the product claim
beyond the existing qualification boundary: FigOps is publication-oriented, and
publishable verdicts still require cited hard-gate evidence.

## Findings

### Journal Track Implementation

FigOps has ten target formats in the live enum, including seven public journal
tracks, `default`, `ppt`, and one internal private track:

```text
acs, cell, default, elsevier, nature, ppt, rsc, science, wiley, <internal-private-track>
```

Seven public journal tracks have distinct encoded baseline tokens:

| Track | Width mm | Height mm | Min font pt | Min line pt | Max height mm | Marker pt | Line pt | Error line pt | Violin width |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| ---:| ---:| ---:|
| nature | 88.0 | 71.0 | 5.0 | 0.25 | 247.0 | 3.2 | 1.2 | 0.8 | 0.52 |
| science | 57.0 | 45.6 | 5.0 | 0.5 | 234.0 | 3.0 | 0.9 | 0.7 | 0.48 |
| acs | 84.67 | 67.736 | 4.5 | 0.5 | 233.0 | 3.4 | 1.0 | 0.75 | 0.5 |
| rsc | 83.0 | 66.4 | 7.0 | 0.5 | 233.0 | 3.3 | 1.0 | 0.75 | 0.5 |
| elsevier | 90.0 | 72.0 | 7.0 | 0.5 | 234.0 | 3.6 | 1.05 | 0.8 | 0.5 |
| wiley | 85.0 | 68.0 | 5.0 | 0.5 | 234.0 | 3.5 | 1.0 | 0.8 | 0.5 |
| cell | 85.0 | 68.0 | 6.0 | 0.5 | 200.0 | 3.4 | 1.0 | 0.8 | 0.5 |

Implementation anchors:

- `hub_core/config_style.py` owns `ALLOWED_TARGET_FORMATS`.
- `themes/style_profiles.py` owns target/profile render tokens and source notes.
- `themes/layout.py` owns absolute-mm layout locking and panel layout presets.
- `hub_core/mcp/tools/render_csv.py` and
  `hub_core/mcp/tools/render_project.py` pass `target_format`, `profile`, and
  `output_format` through style validation, render config generation,
  preflight, geometry diagnostics, and result envelopes.

Conclusion: journal tracks are not superficial labels. They change encoded
geometry/style tokens and feed render/preflight paths. The remaining boundary is
external freshness: the current implementation proves encoded-token compliance,
not latest publisher-rule compliance unless a dated external matrix is added.

### MCP Agent Surface

Canonical MCP tools exposed by live schemas:

```text
figops.health
figops.describe
figops.list_styles
figops.list_projects
figops.inspect_project
figops.validate_project
figops.render_csv_graph
figops.render_csv_multipanel
figops.render_project_figure
figops.collect_artifacts
figops.scaffold_project
figops.normalize_project_structure
figops.batch_check
```

Legacy `graphhub.*` aliases exist for the same 13 tools and map to the same
handlers. Live handler probe found no missing handlers.

Agent-use anchors:

- `docs/internal/protocols/00_agent_graph_workflow.md` defines the default
  direct-FigOps workflow and stop conditions.
- `docs/internal/protocols/05_mcp_tool_playbook.md` maps user intents to tool
  sequences.
- `docs/tools.md` is generated from live schemas and includes input/output
  contracts for render, validation, batch, and artifact tools.
- `figops.describe` exposes plot types, tools, semantic checks, and domain
  helpers for agents at runtime.

Conclusion: all current MCP tools are discoverable and handler-backed for agent
use. Write-capable tools remain policy-gated by MCP config and environment, as
intended.

### Operational Readiness

Current operational controls:

- Latest checked `main` CI run succeeded for commit `e8d6fc7`:
  <https://github.com/Moonweave-Research/figops/actions/runs/28665044401>
- CI has a gating test job plus advisory Ruff and dependency audit jobs.
- CI concurrency cancels superseded runs on the same branch or PR.
- Publish workflow is manual-only, guarded to `refs/heads/main`, builds and
  verifies distributions before upload, and grants `id-token: write` only to
  publish jobs.
- `docs/packaging/trusted-publishing.md` records the TestPyPI/PyPI promotion
  sequence and fresh-install smoke requirements.
- `docs/packaging/public-release-clearance.md` keeps repository-public
  decisions separate from PyPI package distribution.

Current local environment caveat:

- `python hub_uv.py run ...` fails in this shell because `uv` is not on `PATH`.
  This is a correct fail-fast path, but it is an operator-readiness gap for
  local QA. Focused verification was run with the existing Windows-native
  `C:\dev\figops-ascii-venv` environment instead.

Conclusion: release operation is covered, but the next plan should include a
small environment-readiness task so local operators do not confuse a missing
`uv` setup with product failure.

## Verification Evidence

Focused runtime probes:

```bash
C:\dev\figops-ascii-venv\Scripts\python.exe - <<'PY'
from hub_core.config_parser import ALLOWED_TARGET_FORMATS
from hub_core.mcp.schemas import TOOL_NAMES, LEGACY_TOOL_NAMES, get_tool_handlers, list_tool_definitions
from hub_core.mcp import GraphHubMCPServer
from themes.style_profiles import get_render_style_tokens

print(sorted(ALLOWED_TARGET_FORMATS))
for target in ["nature", "science", "acs", "rsc", "elsevier", "wiley", "cell"]:
    print(target, get_render_style_tokens(target, "baseline")[0])
server = GraphHubMCPServer()
print(set(TOOL_NAMES + LEGACY_TOOL_NAMES) - set(get_tool_handlers(server)))
print(len(list_tool_definitions()))
print(server.call_tool("figops.health", {})["structuredContent"]["status"])
PY
```

Observed:

- `target_formats` returned ten entries.
- The seven public journal tracks returned distinct encoded token sets.
- `canonical_tools` was 13, `legacy_tools` was 13, `definitions` was 13.
- `missing_handlers` was empty.
- `figops.health` returned `ok`.

Focused tests:

```bash
C:\dev\figops-ascii-venv\Scripts\python.exe -m pytest \
  tests/test_style_profiles.py \
  tests/test_journal_specs.py \
  tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_tool_definitions_include_read_only_tools_and_schemas \
  tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_list_styles_uses_graph_hub_canonical_contract \
  tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_tool_definitions_include_controlled_rendering_tools \
  tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_csv_graph_schema_exposes_legend_axis_polish_controls \
  -q
```

Result:

```text
28 passed, 7 subtests passed
```

## Next Plan

P0 - Preserve claim boundaries:

- Keep public wording at publication-oriented unless a specific output has a
  rubric-backed `publishable` verdict.
- Preserve the rule that `manual_review_needed=false` is necessary but not
  sufficient for publishable claims.
- Do not market latest publisher compliance beyond the dated
  [journal visual-language matrix](2026-07-04-journal-visual-language-matrix.md)
  and its source-date limitations.
- Treat journal style as three layers:
  - encoded minimum compliance: FigOps tokens, dimensions, preflight checks, and
    geometry diagnostics where measured;
  - authentic visual-language heuristics: source-backed or explicitly
    heuristic differences by journal/track, compared through the
    [journal style-delta report](2026-07-04-journal-style-delta-report.md);
  - evidence-backed publishability review: `publishable` or `journal-ready`
    wording requires cited hard-gate evidence and `manual_review_needed` not
    true.
- Todo 10 dogfood render-pack evidence is expected at
  `.omo/evidence/task-10-journal-style-real-use-hardening-final/render-pack/`;
  it supports review, not automatic acceptance.

P1 - Journal-track fixture qualification:

- Add representative render fixtures for Nature, Science, ACS, RSC, Elsevier,
  Wiley, and Cell.
- Store expected `style_summary`, selected token floors, and
  `geometry_diagnostics`/`layout_report` summaries beside each fixture.
- Include at least one crowded-label and one dense-legend case per fixture pack,
  but keep the verdict publication-oriented unless hard-gate evidence is cited.

P2 - MCP agent consumability guard:

- Add a docs or test guard that compares `TOOL_NAMES`, legacy aliases,
  `list_tool_definitions()`, generated `docs/tools.md`, and the internal agent
  playbook tool lists.
- Fail the guard when a new MCP tool is added without agent-facing workflow
  guidance or generated docs.

P3 - Local operator readiness:

- Add a lightweight local doctor/check command or docs-only target that verifies
  `uv` availability, the external FigOps runtime root, and the active Python
  environment before release QA.
- Keep the current fail-fast `hub_uv.py` behavior; improve the operator path
  around it rather than bypassing it.

P4 - Diagnostic-to-rubric mapping guard:

- Generate or check that every `geometry_diagnostics/1` check maps to `FQ-H*`,
  `FQ-A*`, or explicit informational status.
- Treat `passed is None` for hard-gate diagnostics as unmeasured, not pass.

P5 - Maintenance decomposition:

- Continue behavior-preserving decomposition from the live architecture
  inventory.
- Do not combine broad module movement with visual token changes in one PR.

## Verdict

The current release line passes the post-release total QA re-check for encoded
journal-track differentiation, MCP agent tool availability, and operational
release controls.

Open work is quality hardening, not release repair: fixture qualification,
agent-consumability guards, local environment readiness, diagnostic-to-rubric
mapping, and maintenance decomposition.
