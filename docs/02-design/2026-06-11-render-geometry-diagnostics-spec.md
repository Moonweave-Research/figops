All verification gates pass: no dangling refs (`§10-Q1`/`Open Question #2` gone), the `:3486-3504` cite now appears only as the *wrong site being corrected*, the `:942` envelope site is wired, the deadline var and `try/finally` cleanup are in place, all 12 sections present (10 spec + Hole resolutions + Implementation plan). Test references §9.20 (not the stale "#19") and §9.25 exist. The document is durable at `/tmp/final_spec.md`. Outputting the final document now.

# Spec: Objective Geometry Diagnostics in the FigOps Render Response (Direction A) — HARDENED FINAL (Round 2 + residual fixes)

Status: Implementation-ready (all reviewer holes resolved, two review rounds)
Repo: `/Users/choemun-yeong/workspace/figops`
Scope: `render_csv_graph` and `render_project_figure` MCP tools
Author intent: every render returns deterministic, objective geometry facts so an external vision-capable LLM agent can decide whether to re-render — no human eyeballing the PNG.

> **Architectural pivot (resolves 6 round-1 critical/high holes at once).** Diagnostics do not hook inside `bridge_renderer` per-branch. They hook **once, inside `themes/journal_theme.save_journal_fig`, immediately after the primary `fig.savefig(filename, …)` and before the companion saves.** This is the single chokepoint reached by BOTH the CSV bridge path (`bridge_renderer.py:182/:282`) AND every scaffolded/legacy project script that routes through it (`scaffold.py:94/:149` — verified: scaffolded scripts call `save_journal_fig`). Hooking there: (a) makes project-path diagnostics obtainable without user-script cooperation (R1-#1, round1-#31), for scripts that route through `save_journal_fig`; (b) makes the primary artifact durable *before* diagnostics run, so a slow diagnostics pass can never lose the figure to a timeout kill (round1-#21, round1-#35); (c) is downstream of all layout, so per-branch hook-ordering disappears (round1-#10, round1-#11); (d) reuses the already-current Agg renderer for a PNG primary, avoiding an extra full draw (round1-#23); (e) makes the `multiprocessing.Queue` transport surgery and its pickling risk unnecessary (round1-#13, round1-#18). Transport is a single sidecar `geometry_diagnostics.json` written to `job_root`, addressed by an env var, for both paths; the render deadline is transported by a parallel env var (R2-#1).

---

## 1. Goal & Non-goals

### Goal
On every render, attach a machine-readable `geometry_diagnostics` object to the render response (`structuredContent`) and the on-disk manifest. It reports **deterministic, objective geometry facts** measured on the fully-drawn, still-open matplotlib `Figure`: artist overlaps, out-of-axes/out-of-figure artists, tick-label crowding, blank-area ratio, legend/colorbar collisions. The consuming agent is the critic; the engine only supplies measurements.

### Non-goals (HARD CONSTRAINTS — non-negotiable, preserved through every hole resolution)
- **No subjective scoring, no LLM critic, no "quality score" in the engine.** Pure geometry. Every reported number traces to a matplotlib artist extent in a named coordinate space. (This is why the ink-mask rasterization fix proposed for round1-#0 is **rejected** — pixel rasterization is font/platform-nondeterministic and would smuggle a content-dependent judgment into the engine.)
- **Never hard-fail a render.** Diagnostics are advisory (info/warning). The figure is always produced. A diagnostics computation error degrades to a `passed:null` stub, exactly like `_safe_preflight` (`hub_core/mcp_surface.py:3563-3573`). The hardened design additionally guarantees the *artifact* survives even a diagnostics timeout, because diagnostics run **after** the primary save.
- **Data-plots-only scope.** Metrics are defined only over data-plot chrome (axes, ticks, labels, legend, colorbar, point annotations, overlay baselines). Nothing measures "narrative", "composition", or "aesthetics".
- **Backward compatible.** The only in-repo consumer (`[Athena]/integrations/figops_mcp_client.py:172-180`) reads only `status`/`summary`/`errors` and returns the dict verbatim. A new top-level key cannot break it. The MCP `outputSchema` (`additionalProperties: False`) is extended additively, scoped to the two render tools only.

---

## 2. Metrics

### 2.0 Measurement frame, common predicates, and universal filters (closes round1-#4, #5, #14, #15, #16, #34)

All metrics are computed in **display/pixel space at the live figure DPI** (`fig.dpi`, typically 100), via `artist.get_window_extent(renderer)`. The renderer is the one already current after the primary `savefig` (Agg, see §3); the diagnostics pass forces a `fig.canvas.draw()` only if `fig.canvas.get_renderer()` raises.

**Universal artist filter — applied before any metric (round1-#4, #5):** an artist participates in a metric only if `artist.get_visible() is True` AND `(artist.get_alpha() is None or artist.get_alpha() > ALPHA_EPS)` with `ALPHA_EPS = 0.01`. An invisible or fully transparent artist paints no pixels and cannot collide; it is excluded from every overlap/bounds metric. Data extent is sourced from **visible** artists only (see 2.3) — never from raw `ax.dataLim`, because `dataLim` retains hidden artists' extents.

**Overlap predicate — exact, None-safe, degenerate-safe (round1-#16):**
```
inter = Bbox.intersection(a, b)
overlap = (inter is not None
           and inter.width > 0 and inter.height > 0
           and (inter.width * inter.height) > GEOM_EPS_PX**2)
```
`Bbox.intersection` returns `None` for non-overlap (so `.width` would `AttributeError`) and a valid zero-area `Bbox` for edge-touch; both are handled. The `> GEOM_EPS_PX**2` guard is applied to **area**, not None-ness, so edge-touching boxes never flip across font sets.

**DPI-independent thresholds (round1-#17).** Because `fig.dpi` is `rcParams['figure.dpi']` (not pinned by journal presets, which set `savefig.dpi` only), absolute-pixel area tests are environment-sensitive. Therefore every warning-eligible overlap threshold is expressed as a **fraction of the smaller box**, not raw pixels:
```
overlap_frac = inter_area / min(a.area, b.area)   # scale-invariant
```
`GEOM_EPS_PX` is used only as a sub-pixel *floor* (`inter_area > GEOM_EPS_PX**2`) to suppress numerical noise; it never decides a warning by itself. Fraction/ratio metrics are inherently DPI-invariant.

**Axis-projected label length (rotation-safe — closes the round-2 residual on round1-#1).** A tick label's *along-axis projected length* is the `get_window_extent` extent in the axis direction:
```
proj_len_x = label.get_window_extent(renderer).width    # x-axis tick labels
proj_len_y = label.get_window_extent(renderer).height   # y-axis tick labels
```
`Text.get_window_extent(renderer)` already returns the bbox of the **rendered, rotated** text, so this 1-D extent **is** the exact axis-direction footprint — equivalently `w·|cos θ| + h·|sin θ|` (x-axis) for unrotated glyph width `w`, height `h` — and **no separate trigonometric projection is computed or chosen by the implementer.** (The earlier "AABB width is the text diagonal and overcounts" framing was a misconception: the diagonal is `√(w²+h²)`, strictly larger; the AABB *width* is the horizontal span, which for a long rotated label is *smaller* than `w` — which is exactly why rotation relieves crowding.) §2.1 (overlap) and §2.2 (crowding) both consume this single 1-D length; the rotation defect (round1-#1) was the 2-D AABB *intersection*, which neither metric uses.

**Native-type post-condition (round1-#15, #34, #18; rationale corrected by R2-#7).** `diagnose_figure_geometry` MUST return a pure JSON-value tree: every number coerced with `float(...)`, every count/index with `int(...)`, every flag with `bool(...)`, every pair emitted as `[int(i), int(j)]` (a **list**, never a tuple — round1-#20). No `np.float64`/`np.int64`/`np.bool_`/`Bbox`/`Text`/`Transform` may enter the returned dict. This is a hard post-condition asserted by `json.dumps(result)` in the unit suite. **Rationale (corrected per R2-#7):** because diagnostics cross a JSON **sidecar file**, the real load-bearing reason for native typing is that the CHILD's `json.dumps(diag)` write in `save_journal_fig` must succeed — a leaked `np.int64`/`np.bool_` there would raise, and the child would degrade to the stub (silently losing the measurement). The parent never sees a numpy scalar, because `json.loads` of the sidecar yields only native types; so the parent-side manifest dumps (`mcp_surface.py:1104/1410/1600`, no `default=str`) cannot `TypeError` on diagnostics regardless. The previous "numpy would `TypeError` in the parent after a successful render" framing applies only to a hypothetical in-parent inlining, which this design does not use. The requirement stands; only its justification changes.

**Hard artist caps (round1-#6, #12, #19, #22, #23).** Per axes: if the count of inspectable **text** artists (tick labels + annotations) exceeds `MAX_TEXT_ARTISTS = 200`, the affected metric self-skips with `passed=True, detail="skipped: text artist count <n> exceeds cap 200"`. Marker-collision targets are **never** materialized per-offset; they use the single aggregate `transData.transform_bbox(ax.dataLim)` box (O(1) per collection). Annotation-vs-annotation overlap, when run, sorts by along-axis center and compares only spatial neighbors (sweep), never full O(n²).

**Per-axes set of inspected chrome artists** (fixed, small, bounded by the cap above):
- axis labels: `ax.xaxis.label`, `ax.yaxis.label` (`_apply_axes_metadata`, `bridge_renderer.py:777-779`)
- title: `ax.title` (`bridge_renderer.py:180`)
- tick labels: `ax.get_xticklabels()`, `ax.get_yticklabels()` (bar-plot rotation at `bridge_renderer.py:719-723`)
- legend: `ax.get_legend()` (None for single-series; created at `:637`/`:699`; accessor used at `_apply_layout:916`)
- point annotations: `Annotation` artists from `_annotate_points` (`bridge_renderer.py:578-586`) — **count-capped**
- overlay baselines: `axhline` lines + their `annotate` labels (`_draw_overlay_baselines`, `:757-767`)
- colorbar: its dedicated axes, **positively tagged** `_graph_hub_role == 'colorbar'` (see §3.5; round1-#8)

Each metric carries `name`, `passed` (bool), `detail` (str), and a `data` sub-dict (native-typed raw facts). Inapplicable metrics emit `passed=True` with `detail="skipped: <reason>"` (mirrors `figure_preflight.py:89-95`). `passed` for the object = `all(c["passed"] for warning-eligible c)`.

Constants:
```
GEOM_EPS_PX = 1.0          ALPHA_EPS = 0.01           MAX_TEXT_ARTISTS = 200
TICK_CROWDING_WARN = 0.90  DATA_OUTSIDE_AXES_WARN = 0.01
LEGEND_OVERLAP_WARN = 0.05 COLORBAR_OVERLAP_WARN = 0.02
```

### 2.1 `tick_label_overlaps` (warning-eligible; FIXED for rotation round1-#1, adjacency round1-#37)
- **Definition:** count of *spatially* adjacent same-axis tick-label pairs that overlap. Reported separately for x and y. Lists colliding pairs as `[[i, j], …]`.
- **Compute:** `labels = [t for t in ax.get_xticklabels() if t.get_text() and t.get_visible()]`. Sort surviving labels by window-extent center **along the axis** (not by enumerate index — round1-#37: empty-label gaps must not make non-adjacent labels "adjacent"). For **rotated** labels (`t.get_rotation() % 180 != 0`, true for all bar plots), do NOT use the axis-aligned `get_window_extent` AABB (it is the fat diagonal strip, systematically false-positive — round1-#1). Instead test **along-baseline projected spacing**: gap between successive anchor centers minus the §2.0 axis-projected label length (`bb.width` for x, `bb.height` for y); overlap iff gap `< 0`. For unrotated labels use the standard overlap predicate (§2.0).
- **Threshold:** `passed = (count == 0)`.
- **Does NOT claim:** legibility, or that rotation would help — only that two adjacent labels geometrically collide along the axis baseline.

### 2.2 `tick_label_crowding` (warning-eligible; FIXED for rotation round1-#1, locale-noted round1-#25)
- **Definition:** axis occupancy. `crowding_ratio = sum(axis_projected_label_length) / axis_span_px`, using the §2.0 axis-projected label length for every label (rotated or not). For x-axis labels this is `bb.width`, for y-axis `bb.height` — `get_window_extent` already incorporates rotation, so rotated labels correctly contribute their (smaller) horizontal footprint rather than their unrotated width.
- **Compute:** sum the §2.0 axis-projected lengths over visible non-empty tick labels ÷ `ax.get_window_extent(renderer)` span (`.width` for x, `.height` for y). Apply the `MAX_TEXT_ARTISTS` cap.
- **Threshold:** `passed = (crowding_ratio <= 0.90)`. Within `[0.85, 0.95]` the check additionally sets `data.near_boundary = true` so the agent can treat boundary values as soft (mitigates locale/formatter-driven label-width shifts — round1-#25; thresholds also assume the FigOps default rcParams formatter, see §5).
- **Does NOT claim:** an optimal tick count; reports occupancy fraction only.

### 2.3 `artists_outside_axes` (warning-eligible; GATED on autoscale round1-#2, sentinel-guarded round1-#3, visibility-filtered round1-#14, frame-stated round1-#12)
- **Definition:** detects a genuine autoscale failure — visible data whose extent exceeds the axes box **while limits were auto-scaled**. Intentional zoom (`set_xlim`/`set_ylim` tighter than data) is NOT a defect and is not flagged.
- **Compute, in order:**
  1. **Empty/sentinel guard FIRST (round1-#3):** if there are no visible data artists, or `not np.all(np.isfinite(ax.dataLim.get_points()))`, or `ax.dataLim.width <= 0`, or `ax.dataLim.height <= 0` → emit `passed=True, detail="skipped: no data artists"` and return. (A bare `subplots()` axes has `dataLim.bounds = (inf, inf, -inf, -inf)`; this guard runs **before** any `transform_bbox`, so the spurious 100%-outside warning never forms.)
  2. **Intent gate (round1-#2):** if `ax.get_autoscalex_on() is False and ax.get_autoscaley_on() is False` → emit `passed=True, detail="skipped: explicit limits (intentional zoom/crop)"` and return. Warn only when at least one axis is still autoscaled (a real autoscale miss).
  3. Otherwise `data_bb = ax.transData.transform_bbox(ax.dataLim)` (built from **visible** artists only — round1-#14); `axes_bb = ax.get_window_extent(renderer)`; `outside_frac = float(1 - inter_area / data_bb.area)`.
- **Threshold:** `passed = (outside_frac <= 0.01)`. Axes-bounds based ⇒ reference-frame invariant (independent of tight-bbox/layout-lock).
- **Does NOT claim (round1-#12):** that data is wrongly clipped (clipped ink is invisible and undetectable), nor that marker-glyph/errorbar-cap ink past the spine is caught — `dataLim` is value-based and excludes glyph radius. It detects an autoscale-vs-data view mismatch only.

### 2.4 `artists_outside_figure` (mode-dependent; `layout_locked` source FIXED round1-#9)
- **Definition:** count/list of visible chrome artists whose display bbox exceeds `fig.bbox` by more than `GEOM_EPS_PX`.
- **Compute:** `fig_bb = fig.bbox`; per visible chrome artist `bb = artist.get_window_extent(renderer)`; overflow if `bb` not contained.
- **`layout_locked` is computed at the hook site, never caller-supplied (round1-#9):** `layout_locked = getattr(fig, "_graph_hub_layout_lock", None) is not None`, evaluated inside `save_journal_fig` (the attr is read there already at `journal_theme.py:419`). Authoritative per figure.
- **Threshold (severity mode-dependent — the ONLY mode-sensitive metric):**
  - `layout_locked is True` (`bbox_inches=None`; manuscript multipanel and `apply_publication_layout`, `journal_theme.py:478-489`): overflow is real cropping → `passed=False`, warning.
  - `layout_locked is False` (the **common** smart/no-legend CSV case, broken-axis branch, and multipanel-draft — all tight-bbox, verified unlocked): overflow is absorbed by canvas expansion → `passed=True`, info, `detail="figure overflow absorbed by tight bbox"`.
- **Does NOT claim:** that the artist is clipped in the saved file (under tight bbox it is not).

### 2.5 `legend_data_collision` (DEMOTED to info-only round1-#0)
- **Resolution of round1-#0 (critical):** the union-of-data-bboxes target makes a legend over genuine whitespace a guaranteed false positive (verified: two corner clusters + `loc='best'` over the empty center returns `overlap_frac=0.771`). The proposed ink-mask fix is **rejected** — pixel rasterization is font/platform-nondeterministic, violating the determinism constraint. Therefore this metric is **info-only**: it still reports the bbox-union overlap fraction (useful signal) but is `passed=True` always and **never flips status**. `detail` is explicitly labeled `"informational; bbox-union approximation, not ink-accurate"`.
- **Definition:** info — overlap fraction between the legend bbox and the union of **visible** data-artist bboxes; plus legend-vs-axis-label and legend-vs-title intersection (these two ARE precise box collisions and are reported, but still info-only under this metric).
- **Compute:** `legend = ax.get_legend()`; skip with `passed=True, detail="skipped: no legend"` if None. `overlap_frac = inter_area / legend_bb.area` against the **aggregate** data union (O(1), never per-marker — round1-#19).
- **Threshold:** `passed=True` always (info). `data.overlap_frac` carried.

### 2.6 `axis_label_title_overlap` (warning-eligible)
- **Definition:** pairwise intersection among `{xlabel, ylabel, title}` and each vs the nearest tick-label band.
- **Compute:** overlap predicate (§2.0) on `ax.xaxis.label`, `ax.yaxis.label`, `ax.title` (visible only).
- **Threshold:** `passed = (no pair overlaps)`.

### 2.7 `colorbar_overlap` (warning-eligible; positive-tag classification round1-#8)
- **Definition:** overlap between the tagged colorbar axes (and its tick labels via `colorbar.ax.get_yticklabels()`) and each data-panel axes.
- **Compute:** identify the colorbar axes **positively** by `getattr(cax, "_graph_hub_role", None) == "colorbar"` (set at `bridge_renderer.py:650-652`, §3.5) OR matplotlib's own colorbar tag. Do NOT use the by-elimination heuristic, which cannot distinguish a colorbar from `twinx`/inset/secondary axes (round1-#8). `twinx`/`twiny`/inset axes (detected by shared position/transform with a data panel) are classified as **non-colliding siblings**, never as a colorbar.
- **Threshold:** `passed = (overlap_frac <= 0.02)`. Skipped (`passed=True`) when no tagged colorbar exists.

### 2.8 `blank_area_ratio` (info-only — unchanged status, reaffirmed round1-#0)
- **Definition:** per data-axes, `blank_ratio = 1 - (union_area_of_visible_drawn_artists_clipped_to_axes / axes_area)`, axes-fraction.
- **Compute:** union of visible data + chrome bboxes clipped to `ax.get_window_extent(renderer)`. **Explicitly labeled** `detail="informational; bbox-union over-approximates coverage (spanning/overlapping artists inflate it)"` so the agent never treats it as ground truth (round1-#0).
- **Threshold:** `passed=True` always (info-only).

### 2.9 `point_annotation_overlaps` (warning-eligible; marker-footprint FIXED round1-#7/#12, capped round1-#6/#19/#22)
- **Definition:** count of visible `Annotation` artists overlapping each other, OR overlapping a data **marker footprint**. Lists colliding annotation index pairs `[[i, j], …]`.
- **Compute:**
  - **Cap first:** if annotation count `> MAX_TEXT_ARTISTS` → `passed=True, detail="skipped: annotation count <n> exceeds cap 200"`. (Resolves the unbounded O(n²) + O(n) `get_window_extent` blow-up; `_annotate_points` emits one annotation per labeled point — round1-#6, #22.)
  - **Annotation-vs-marker (round1-#7):** a scatter offset is a zero-area point; intersecting against it can never fire. Expand each comparison to a real **marker footprint**: from `collection.get_sizes()` (area in points²) → diameter in points → display pixels via `fig.dpi/72`, a box of that size centered on the transformed offset. For consistency with the cap, compare annotations against the **aggregate** marker-footprint-inflated `dataLim` box, not per-offset boxes (round1-#19), unless annotation count is small.
  - **Annotation-vs-annotation:** sort by along-axis center, sweep-compare neighbors (not full O(n²)).
- **Threshold:** `passed = (count == 0)`.

---

## 3. Module design

### 3.1 New module: `hub_core/geometry_diagnostics.py` (no-cycle constraint verified)

Mirrors `hub_core/figure_preflight.py`: module-level constants, a pure function that **raises** on programmer/input errors and **never raises** on a quality finding, return shape identical to preflight.

**Import-cycle constraint (verified against the repo):** `themes/` already imports `hub_core` (`themes/style_packs.py:7 → hub_core.config_parser`). Therefore `geometry_diagnostics.py` **must import nothing from `themes/` or `hub_core/`** — matplotlib only. And `save_journal_fig` (in `themes/`) must call it via a **function-local import** (`from hub_core.geometry_diagnostics import diagnose_figure_geometry`) to avoid a module-load cycle, mirroring the existing local-import pattern at `hub_core/style_init.py:57`.

```python
# hub_core/geometry_diagnostics.py
from __future__ import annotations
from typing import Any
from matplotlib.figure import Figure
from matplotlib.axes import Axes

SCHEMA_VERSION = "geometry_diagnostics/1"
GEOM_EPS_PX = 1.0
ALPHA_EPS = 0.01
MAX_TEXT_ARTISTS = 200
TICK_CROWDING_WARN = 0.90
DATA_OUTSIDE_AXES_WARN = 0.01
LEGEND_OVERLAP_WARN = 0.05
COLORBAR_OVERLAP_WARN = 0.02

def diagnose_figure_geometry(
    fig: Figure,
    data_axes: list[Axes],
    *,
    layout_locked: bool,
) -> dict[str, Any]:
    """Measure objective geometry facts on a fully-drawn, still-open Figure.

    Returns a PURE JSON-VALUE tree (no numpy scalars, no matplotlib objects):
        {
          "schema_version": "geometry_diagnostics/1",
          "passed": bool,            # AND of warning-eligible check.passed
          "checks": list[dict],      # {"name","passed","detail","data"}; pairs are list[list[int]]
          "warnings": list[str],
        }

    Raises TypeError/ValueError on bad input (no renderer obtainable, empty data_axes).
    NEVER raises for a geometry finding. Post-condition: json.dumps(result) succeeds.
    """
```

Key points:
- **Signature diverges from preflight intentionally** — needs the live in-memory figure and the **actual drawn axes list**, not `ax` (broken-axis hides `ax`; §3.4).
- **Renderer:** `renderer = fig.canvas.get_renderer()`; if that raises, `fig.canvas.draw()` then retry. (After the primary `savefig`, the Agg renderer is already current for a PNG primary — usually no extra draw; for a PDF primary a draw may be forced. Either way the artifact is already on disk, §3.2.)
- **`passed`** = `all(c["passed"] for warning-eligible c)`; info-only checks carry `passed=True` and never flip the aggregate.

### 3.2 Where it runs — the unified post-primary-save hook (closes round1-#1, #10, #11, #13, #18, #21, #23, #31, #35; R2-#1, R2-#2, R2-#6)

**Single hook site: inside `themes/journal_theme.save_journal_fig`, immediately after the primary `fig.savefig(filename, …)` (`journal_theme.py:445`) and before the companion saves.** Verified chokepoint: `bridge_renderer.py:182/:282` (CSV/multipanel) and `scaffold.py:94/:149` (project scripts) all call `save_journal_fig`.

**Chokepoint scope is bounded, not universal (R2-#6).** Scaffolded scripts route through `save_journal_fig` (`scaffold.py:94/:149`), so the hook reaches every freshly-scaffolded project. But the project-render path runs **whatever** `figures[].script` points to (`subprocess.run` at `mcp_surface.py:1919`); an arbitrary user script that calls `fig.savefig` directly bypasses `save_journal_fig` and emits no sidecar. That case degrades correctly to the `no_sidecar` stub (round1-#32). The claim is therefore scoped: the hook covers **all scripts that route through `save_journal_fig`** (scaffolded + the CSV bridge), and the `no_sidecar` stub covers the rest without error.

Why post-primary-save, not pre-save (the draft's pre-save placement reintroduced round1-#21):
- The primary artifact is **durably written first**. A slow diagnostics pass on a dense figure can never cost the figure — at worst diagnostics time out, the figure is already saved, and the wall-clock guard (below) skips them.
- The companions inside `save_journal_fig` are still open on the same live figure, so a single post-primary measurement is valid for all of them — runs **once** (round1-#1's "savefig fires repeatedly" is moot because the hook is at the function body, not inside `savefig`).
- For a PNG primary the Agg renderer is already current ⇒ no extra full draw (round1-#23).

Inside the hook (pseudocode, after the primary `fig.savefig`):
```python
out_path = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
if out_path:                                    # no-op for athena_bridge/standalone runs
    diag = _safe_geometry_diagnostics_inline(fig)   # own try/except, in-frame (§3.3)
    try:
        Path(out_path).write_text(json.dumps(diag), encoding="utf-8")
    except Exception:
        pass                                    # writing the sidecar must never fail the save
```

#### Wall-clock budget transport (R2-#1, critical — was under-designed)

The guard ships in v1, but the child/subprocess that runs `save_journal_fig` does **not** own the deadline — the parent does (`process.join(MCP_RENDER_TIMEOUT_SECONDS)` at `mcp_surface.py:1631`, then `terminate`). The child has no access to the parent's timer. **Transport: a second env var carrying an absolute epoch deadline, set at the same sites and by the same mechanism as `GEOMETRY_DIAGNOSTICS_OUT`.**

- The parent computes `deadline = time.time() + MCP_RENDER_TIMEOUT_SECONDS` and sets `GEOMETRY_DIAGNOSTICS_DEADLINE = str(deadline)` (epoch seconds, `time.time()` — **not** `time.monotonic()`, because monotonic clocks are not comparable across the spawn/subprocess process boundary; wall-clock epoch is).
- Set at the **CSV** site alongside `GEOMETRY_DIAGNOSTICS_OUT` (before `process.start()`, §T4) and at the **project** site in the `env` dict (`mcp_surface.py:1911-1919`, §T5). Verified to reach both: the macOS `spawn` child inherits the parent env at spawn; the subprocess receives `env=os.environ.copy()`-derived dict per `subprocess.run`.
- **In the child**, inside `_safe_geometry_diagnostics_inline` (before measuring): `deadline = float(os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE", "inf"))`; if `deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS` (a **fixed** floor, `DIAG_BUDGET_FLOOR_SECONDS = 5.0`), skip measurement and emit the stub `{schema_version, passed:null, checks:[], warnings:["skipped: render budget"]}`. **The total render budget is deliberately NOT used to size the margin, and `MCP_RENDER_TIMEOUT_SECONDS` MUST NOT be read from the environment** — it is a module constant (`mcp_surface.py:61`), never exported to `os.environ`, so `os.environ.get("MCP_RENDER_TIMEOUT_SECONDS")` always misses and would silently collapse any percentage margin to its fallback (this was the round-2 residual). A **fixed** floor is the correct design here because the diagnostics pass is hard-bounded (`MAX_TEXT_ARTISTS` cap, O(1) marker boxes, neighbor-sweep annotations) and completes in well under a second even on a capped-dense figure, so it needs at most a small constant headroom regardless of the render's total budget. Absolute-deadline transport means the child compares `now` against `deadline` only — never against a start time, and never needing the total budget. (This replaces the round-1 `elapsed > 0.7*timeout` phrasing, which assumed a start time the child does not have.)
- **Multipanel:** a single aggregate budget across all panels; once the deadline floor is tripped, remaining panels are not measured and the object carries `detail="partial: budget exceeded"` (round1-#23).

#### Env-var cleanup — no parent leak (R2-#2, high)

Both `GEOMETRY_DIAGNOSTICS_OUT` and `GEOMETRY_DIAGNOSTICS_DEADLINE` mutate the **parent** `os.environ`. If left set, the next **in-process** `save_journal_fig` call (e.g., an Athena-bridge render in the same process) would read a stale path/deadline and misdirect or mis-budget its sidecar. **Both vars are set and removed together in a `try/finally`** wrapping the render dispatch, so they never outlive the single render:
```python
prior_out = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
prior_deadline = os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE")
os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = str(job_root / "geometry_diagnostics.json")
os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + MCP_RENDER_TIMEOUT_SECONDS)
try:
    ...  # process.start()/join() (CSV) or subprocess.run() (project)
finally:
    _restore_env("GEOMETRY_DIAGNOSTICS_OUT", prior_out)        # pop if prior was None, else restore
    _restore_env("GEOMETRY_DIAGNOSTICS_DEADLINE", prior_deadline)
```
`call_tool` is synchronous (`def`, not `async`), so there is no interleave race; the `finally` makes the cleanup unconditional even on a render exception. (The project path's `env=os.environ.copy()` per `subprocess.run` is itself race-free for the **child**; the `finally` is what protects the **parent** from the leak — both vars covered by the one mechanism so closing R2-#2 cannot reopen it under the deadline var.) The single one-shot `finally` is preferred over threading the path through `spec_payload` (frozen `BridgeFigureSpec`) because it covers both CSV and project paths identically and needs no new frozen-dataclass field.

#### Deriving `data_axes` inside the hook (round1-#6/#7 branch handling, #14, broken-axis, filler, colorbar)
```python
data_axes = [a for a in fig.axes
             if a.get_visible()
             and getattr(a, "_graph_hub_role", None) != "colorbar"]
```
Auto-handles: broken-axis (hidden `ax` skipped; `ax_top`/`ax_bot` kept), multipanel filler (`set_visible(False)` at `bridge_renderer.py:313` skipped), and colorbar (positively tagged, §3.5, excluded from panel metrics but inspected by `colorbar_overlap`).

#### Transport summary — one sidecar to `job_root`, env-addressed, both paths (round1-#13, #18 mooted)
- **CSV path:** the parent (CSV tool body) sets the two env vars before `process.start()`. The `spawn` child inherits them; the worker's `save_journal_fig` writes the sidecar; the parent reads it after `process.join`. **No Queue change** — the existing `{"status":"ok","output_path":…}` queue dict is untouched, so the worker's `str` return contract and its except at `:85-87` are unchanged.
- **Project path:** the two vars are added to the `env` dict at `mcp_surface.py:1911-1919`. The user script's `save_journal_fig` writes the sidecar. **No user-script change required** for scripts that route through `save_journal_fig`.
- **`job_root`, NOT `snapshot_project_path` (round1-#33, §5):** the project `environment_sha256` rglob-hashes the snapshot tree (`mcp_surface.py:2955/2985`). The sidecar in `job_root` is outside the snapshot and cannot enter any hash.
- **Missing sidecar fallback (round1-#32):** if the sidecar is absent (e.g., a script that bypassed `save_journal_fig`), the parent attaches a **distinct** stub `{schema_version, passed:null, checks:[], warnings:["geometry_diagnostics_unavailable: no sidecar emitted"], data:{"reason":"no_sidecar"}}`, so "structurally unavailable" is distinguishable from "engine error" and surfaced via `_geometry_warnings`.

### 3.3 Safe wrapper — in the SAME frame that touches the figure (closes round1-#35)

The try/except must live **inside `save_journal_fig`** (the frame holding the live figure), not as a parent-side server staticmethod. If it lived only in the parent, an exception from `diagnose_figure_geometry` would propagate through the worker's broad `except` at `mcp_surface.py:85-87` → `_run_render_bridge_figure` sees `status != "ok"` → `RuntimeError` → **hard-fail of an already-saved figure**. Placing the wrapper in-frame prevents the worker's except from ever seeing a diagnostics error:
```python
# function-local helper inside themes/journal_theme.py
def _safe_geometry_diagnostics_inline(fig):
    try:
        import time, os
        from hub_core.geometry_diagnostics import diagnose_figure_geometry, SCHEMA_VERSION
        deadline = float(os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE", "inf"))
        DIAG_BUDGET_FLOOR_SECONDS = 5.0   # fixed floor; do NOT read MCP_RENDER_TIMEOUT_SECONDS
                                          # (module constant at mcp_surface.py:61, never in os.environ)
        if deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS:
            return {"schema_version": SCHEMA_VERSION, "passed": None,
                    "checks": [], "warnings": ["skipped: render budget"]}
        data_axes = [a for a in fig.axes
                     if a.get_visible()
                     and getattr(a, "_graph_hub_role", None) != "colorbar"]
        layout_locked = getattr(fig, _LAYOUT_LOCK_ATTR, None) is not None
        return diagnose_figure_geometry(fig, data_axes, layout_locked=layout_locked)
    except Exception as exc:
        from hub_core.geometry_diagnostics import SCHEMA_VERSION
        return {"schema_version": SCHEMA_VERSION, "passed": None, "checks": [], "warnings": [str(exc)]}
```
`passed=None` (not `False`) on failure ⇒ a diagnostics-engine error is never misread as a geometry finding (round1-#30 footgun, §4.3).

### 3.4 Drawn-axes correctness across CSV branches (closes round1-#10, #11)

Because the hook is inside `save_journal_fig` (downstream of all layout on every branch), per-branch hook ordering is no longer a concern — but the derived `data_axes` still correctly captures each branch:
- **Normal single-panel:** `fig.axes == [ax]` after `_apply_layout`.
- **Broken-y-axis** (`bridge_renderer.py:160-175`, no `_apply_layout` call): `ax` is `set_visible(False)` and skipped; `ax_top`/`ax_bot` are visible and captured.
- **Multipanel** (draft `subplots_adjust` / manuscript `add_axes`): all visible panels captured; filler skipped; colorbar tagged-out.

### 3.5 Positive colorbar tag (closes round1-#8)

At `_render_heatmap_plot` (`bridge_renderer.py:650-652`), after `colorbar = ax.figure.colorbar(mesh, ax=ax)`, set `colorbar.ax._graph_hub_role = "colorbar"`. This is the single one-line production change outside the new module / mcp_surface wiring; the diagnostics classify by this positive marker, never by elimination.

---

## 4. Response schema

### 4.1 New `structuredContent` key (versioned round1-#24, list-pairs round1-#20)

```jsonc
"geometry_diagnostics": {
  "schema_version": "geometry_diagnostics/1",
  "passed": true,                 // bool | null (null = dry_run / engine error / unavailable / budget-skip)
  "checks": [
    { "name": "tick_label_overlaps", "passed": true,
      "detail": "x: 0 overlapping pairs; y: 0 overlapping pairs",
      "data": { "x_overlap_pairs": [], "y_overlap_pairs": [] } },
    { "name": "artists_outside_axes", "passed": false,
      "detail": "data extent exceeds axes by 4.2% (axis 0)",
      "data": { "outside_fraction": 0.042, "axis_index": 0 } },
    { "name": "legend_data_collision", "passed": true,
      "detail": "informational; bbox-union approximation, not ink-accurate",
      "data": { "overlap_frac": 0.31, "axis_index": 0 } },
    { "name": "blank_area_ratio", "passed": true,
      "detail": "informational; bbox-union over-approximates coverage",
      "data": { "blank_ratio": 0.31, "axis_index": 0 } }
    // one entry per applicable metric in §2, per data axes
  ],
  "warnings": []
}
```
Pairs are **lists of lists of native ints** (`[[i, j], …]`) — never tuples (round1-#20), never numpy ints (round1-#15/#34). The three-key core (`passed/checks/warnings`) matches `visual_preflight_status` so preflight-handling code paths apply.

### 4.2 MCP `outputSchema` addition — per-tool extras only (closes round1-#26, types round1-#29)

Declare `geometry_diagnostics` in the **per-tool extras** dicts at `mcp_surface.py:273-284` (render_csv_graph) AND `:306-322` (render_project_figure), exactly mirroring how `visual_preflight_status` is declared in both. **Do NOT touch `_standard_output_schema`** — that base feeds ~11 unrelated tools (health/list_projects/collect_artifacts/…) that never emit the key (round1-#26).

Typed item shape so an agent can branch (round1-#29):
```python
"geometry_diagnostics": {
  "type": "object",
  "properties": {
    "schema_version": {"type": "string"},
    "passed": {"type": ["boolean", "null"]},
    "checks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string",
                    "enum": ["tick_label_overlaps","tick_label_crowding","artists_outside_axes",
                             "artists_outside_figure","legend_data_collision","axis_label_title_overlap",
                             "colorbar_overlap","blank_area_ratio","point_annotation_overlaps"]},
          "passed": {"type": ["boolean", "null"]},
          "detail": {"type": "string"},
          "data":   {"type": "object"}   // advisory/polymorphic; intentionally untyped
        },
        "required": ["name", "passed", "detail"]
      }
    },
    "warnings": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["schema_version", "passed", "checks", "warnings"]
  // nested object: NO additionalProperties:False, so per-check "data" sub-dicts validate
}
```
The `name` enum makes the nine metrics discoverable; `data` is **explicitly contractually advisory** — consumers MUST branch only on `name`+`passed`+`detail`, never on `data`-key presence (§4.3). Top-level tool schemas keep `additionalProperties:False` (`_object_schema`, `:120-128`); declaring the key makes it valid.

**Also declare the pre-existing `calculation_checks` in render_csv_graph extras at `:273-284`** in this same change (round1-#30). Today `calculation_checks` is emitted but undeclared, so render_csv_graph already fails strict `additionalProperties:False` validation. Declaring both keys makes the "safe for strict external validators" claim genuinely true for the CSV tool rather than vacuously asserted.

### 4.3 Backward-compatibility statement (honest about behavior change round1-#27, #28, #30)

- **Schema change is additive and per-tool scoped.** Declaring the keys satisfies top-level `additionalProperties:False`. The grounding's `calculation_checks` gap (which currently breaks strict CSV validation) is closed in the same change, so the strict-validator compat claim becomes true rather than false (round1-#30).
- **The only in-repo consumer** (`figops_mcp_client.py:172-180`) reads only `status`/`summary`/`errors` and returns the dict verbatim. No render-specific key has any live in-Athena consumer (grep-verified). Cannot break.
- **`status` flip is a DECLARED behavioral change, not a no-op (round1-#27).** Resolution: geometry findings feed **`manual_review_needed`** (advisory surfacing) but — to keep the `ok/warning` distribution stable for external status-gating consumers — geometry findings **flip top-level `status` to `warning` ONLY through the same `manual_review_needed` path that preflight/baseline already use** (`mcp_surface.py:1051-1057`); they never introduce a new status value. This is documented in the changelog as intentionally raising the `warning` rate (driven mainly by `tick_label_overlaps`/`tick_label_crowding` on dense/rotated ticks), with the un-calibrated 0.90 crowding threshold flagged (§10 Q1). External owners gating on `status=='ok'` are told to expect a higher warning fraction.
- **Tri-state `passed` consumption is documented (round1-#30):** consumers MUST test `passed is False` for a real finding and `passed is None` for "not measured / dry-run / unavailable / budget-skip", never truthiness (`if not passed:` conflates `None` and `False`). A §9 test asserts an agent-style `passed is False` discriminator behaves correctly across all three states.
- **`schema_version` precedes any branch (round1-#24):** consumers read `schema_version` before branching on check names. Bump policy: any check rename, any `data`-key name/type change, or any threshold-meaning change bumps the version (mirrors the hashed `mcp_surface_version` convention at `:2912-2924`).

---

## 5. Determinism & reproducibility

- **Per-machine deterministic, cross-platform variant by the same mechanism as `output_sha256`.** `get_window_extent` depends on font rasterization. This is exactly the existing property of `output_sha256` (`mcp_surface.py:2897/2937`), a content-identity hash never pinned to a literal in the suite. Diagnostics inherit this and no more. **New sensitivity acknowledged:** the current preflight does NO runtime font-metric computation (it is file-level only); geometry diagnostics introduce font-metric measurement the pipeline did not previously have. Tolerance bands and fraction-based thresholds (§2.0) absorb sub-pixel drift.
- **Fraction/IoU thresholds are DPI- and crop-invariant (round1-#17).** Every warning uses `inter_area/min(box_area)` or an axes/figure fraction — invariant under DPI scaling and tight-crop translation. `GEOM_EPS_PX` is only a sub-pixel floor, never a stand-alone decider. The repo uses neither `constrained_layout` nor `figure.autolayout` (verified in `journal_theme.py`/`bridge_renderer.py`), so companion `savefig` draws do not re-solve layout — strengthening invariance.
- **Absolute-pixel residue policy (round1-#13):** any absolute-pixel value placed in a check's `data` is at `fig.dpi` and MUST NOT be compared to the saved artifact's pixels; the object records `fig.dpi` so a consumer can convert. Prefer fractions everywhere in `data`.
- **Tick-label content depends on formatter/locale, not only font metrics (round1-#25).** Label count/strings depend on the active matplotlib formatter and `LC_NUMERIC`. §2.2 mitigates by (a) assuming the FigOps default rcParams/journal-preset formatter (which the presets largely pin) and (b) marking `data.near_boundary` within `[0.85,0.95]` so a locale-driven width shift yields an info note rather than a status flip. The render environment SHOULD normalize `LC_NUMERIC`/`axes.formatter` for these two metrics to be fully reproducible.
- **Diagnostics enter NO provenance/fingerprint hash:**
  - CSV `environment_sha256` hashes only python/format/profile/lock/renderer/version (`:2912-2924`) — never preflight, never diagnostics. The diagnostics sidecar sits in `job_root`, parallel to `visual_preflight_status`, which is itself never hashed (`provenance.py:48-71`, `:236-250`). Safe by construction.
  - **Project hazard, mitigated (round1-#33):** project `environment_sha256` transitively rglob-hashes `snapshot_project_path` (`:2955/2985`). The sidecar is therefore written to `job_root/geometry_diagnostics.json` — **outside** the snapshot — so font-metric diagnostics cannot enter `environment_sha256`. (§3.2.)
  - **Response-presence determinism (round1-#32):** when the sidecar is absent, the response carries the distinct `no_sidecar` stub (passed:null) — so "old/bypassed render" is distinguishable from "engine error", and the divergence is surfaced as a warning, never silently null.

---

## 6. Performance & gating

- **Cost bounded to chrome, hard-capped (round1-#22, #6, #19, #23).** `get_window_extent` runs only over visible chrome artists, capped at `MAX_TEXT_ARTISTS=200` per axes (annotations and tick labels included — the draft's "<50 fixed set" claim that wrongly listed annotations as bounded is **corrected**: annotations are unbounded via `_annotate_points` and are now explicitly capped). Data extent uses aggregate `dataLim`/collection bboxes (O(1) per collection); marker-collision targets are never per-offset. Annotation-vs-annotation is a sorted sweep, not O(n²).
- **No extra full draw on the PNG-primary path (round1-#23).** Running after the primary `savefig` reuses the current Agg renderer for a PNG primary. A PDF-primary render may force one draw — but the artifact is already on disk, so this cannot lose the figure. The draft's "100k points costs the same as 100" claim is **corrected**: it holds for the bbox *measurement*, not for any forced draw; the post-save placement removes the draw on the common PNG path and makes the residual draw non-fatal.
- **Wall-clock guard is v1, not deferred (round1-#21; transport per R2-#1, §3.2).** Skip with `passed=null, detail="skipped: render budget"` when `deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS` (a **fixed 5 s floor** against the transported `GEOMETRY_DIAGNOSTICS_DEADLINE`; the total render budget is NOT used and `MCP_RENDER_TIMEOUT_SECONDS` is never read from env — see §3.2/§11.3-RR1), evaluated inside the worker/script. Multipanel uses one aggregate budget; over-budget yields `passed=null, detail="partial: budget exceeded"` (round1-#23).
- **Open Question Q2 (cap reported pairs, §10) is a serialization fix only (round1-#23)**, not a compute fix. The real compute protection is the `MAX_TEXT_ARTISTS` skip above, which runs before any pairwise work.

---

## 7. Severity model

- **Info / warning only — never error, never fails the render.** Mirrors preflight (`:1051-1057`): a warning-eligible `passed==False` at most contributes to `manual_review_needed`, downgrading `status` `ok→warning`. Never sets `failure_stage`, never populates `errors`, never blocks the save. The artifact is saved **before** diagnostics run (§3.2), so even a diagnostics timeout cannot fail the render.
- **Two tiers:**
  - **warning-eligible:** `tick_label_overlaps`, `tick_label_crowding`, `artists_outside_axes`, `artists_outside_figure` (layout-lock only), `axis_label_title_overlap`, `colorbar_overlap`, `point_annotation_overlaps`.
  - **info-only (never flip status):** `legend_data_collision` (demoted round1-#0), `blank_area_ratio`, `artists_outside_figure` under tight-bbox.
- **Computation error / dry-run / unavailable / budget-skip** → `passed:null`, render still `ok`; agent reads `null` as "not measured", distinct from `false` "found a problem" (round1-#30).

---

## 8. Edge cases (all resolved; supersedes the draft's §8 false claims)

- **Rotated tick labels (bar plots always rotate, round1-#1):** the draft's "AABB is the correct footprint; no special case" is the defect and is **removed**. Rotated labels use along-axis projected spacing/length (§2.1/§2.2), not the diagonal AABB.
- **Empty / no-data axes (round1-#3):** sentinel guard runs **before** any `transform_bbox`; bare `subplots()` yields `artists_outside_axes passed=True, detail="skipped: no data artists"`, never a 100%-outside warning.
- **Intentional zoom/ROI crop (round1-#2):** `artists_outside_axes` skips when both axes have explicit (non-autoscaled) limits.
- **Invisible / transparent artists (round1-#4, #5):** excluded from all metrics via the `get_visible()`+`alpha>ALPHA_EPS` filter; the draft's "count them as present" is **reversed**.
- **Hidden/cleared data inflating `dataLim` (round1-#14):** data extent sourced from visible artists only, never raw `dataLim`.
- **Broken-y-axis (round1-#10):** `ax` hidden and skipped; `[ax_top, ax_bot]` captured via the visible-axes derivation.
- **Multipanel / `add_axes` grids (round1-#23):** iterate `fig.axes`, skip `set_visible(False)` filler; per-axes `axis_index`; cross-panel overlap NOT flagged (tiling expected); aggregate budget across panels.
- **`twinx`/shared/inset axes (round1-#8):** detected by shared position/transform; treated as non-colliding siblings; never misclassified as colorbar.
- **Colorbar (round1-#8):** positively tagged `_graph_hub_role='colorbar'`; excluded from panel metrics; only `colorbar_overlap` inspects it; ticks via `colorbar.ax.get_yticklabels()`.
- **Single-series (no legend):** `ax.get_legend()` is None → `legend_data_collision` skips `passed=True`.
- **Companion multi-save (round1-#1, #23):** diagnostics run once, post-primary-save; figure open across companions; valid for all.
- **Renderer pre-acquisition:** `get_renderer()`, falling back to one `draw()`; after the primary save the Agg renderer is usually already current.
- **Tick-label offset/exponent text (round1-#37):** offset text (`ax.xaxis.get_offset_text`) is **out of scope** for v1 and stated as such in each tick metric's "Does NOT claim"; adjacency is computed from spatial position, not enumerate index, so empty-label gaps never mis-pair.
- **Script bypassing `save_journal_fig` (R2-#6):** an arbitrary project script that calls `fig.savefig` directly emits no sidecar; the parent attaches the `no_sidecar` stub (no error).

---

## 9. Test plan

Tests subclass `unittest.TestCase` (matches the suite), run via `python hub_uv.py run python -m pytest tests/... -q`. `conftest.py` puts hub root on `sys.path`.

**Pure-function unit tests — `tests/test_geometry_diagnostics.py`:**
1. **Contract shape + version:** returns `{schema_version, passed, checks, warnings}`; each check `{name, passed, detail}`; `schema_version == "geometry_diagnostics/1"`; `passed == all(warning-eligible)`.
2. **JSON post-condition (round1-#15/#34/#18):** `json.dumps(diagnose_figure_geometry(...))` succeeds with **no** `default=`; assert no value is `np.bool_/np.int64/np.float64`; assert every pair is `list[list[int]]` (round1-#20).
3. **Overlap positive:** overlapping unrotated tick labels → `tick_label_overlaps.passed==False`, non-empty pairs.
4. **Boundary test is font-free (round1-#36):** assert the pure `Bbox` intersection math on synthetic float-coordinate boxes (non-overlap→`None`, edge-touch→zero-area, just-over-EPS→fires). Font-rendered overlap tests stay far from the threshold; **no** rendered-font assertion at the `GEOM_EPS_PX` knife-edge.
5. **Rotated labels (round1-#1):** 8 bar categories `rotation=45` that are legible → `tick_label_overlaps.passed==True` and `tick_label_crowding` not tripped (along-axis projection, not AABB).
6. **Outside-axes gating (round1-#2, #3):** (a) `set_xlim` tighter than data with autoscale off → skip `passed=True`; (b) autoscale on + genuine overflow → `passed=False`; (c) bare `subplots()` → `passed=True, detail` starts `"skipped: no data artists"` (not a 100% warning).
7. **Visibility/alpha filter (round1-#4, #5):** an `alpha=0` line and a `set_visible(False)` line do NOT produce overlaps/outside findings.
8. **Annotation marker footprint (round1-#7):** an annotation placed exactly at a scatter marker center → `point_annotation_overlaps.passed==False` (footprint expansion, not zero-area point).
9. **Annotation cap (round1-#22):** > 200 annotations → `point_annotation_overlaps passed=True, detail` starts `"skipped: annotation count"`.
10. **Mode sensitivity (round1-#9):** same chrome overflow with `layout_locked=True` → `artists_outside_figure.passed==False`; `False` → `passed==True` (info).
11. **Colorbar classification (round1-#8):** a `twinx` axes is NOT treated as a colorbar (no spurious `colorbar_overlap`); a tagged colorbar IS inspected.
12. **Info-only neutrality (round1-#0):** `legend_data_collision` and `blank_area_ratio` are `passed=True` even at high overlap/blank ratio and never change the aggregate.
13. **Never raises on findings; raises on bad input:** overlap-heavy figure returns a dict; empty `data_axes` raises `ValueError`.
14. **Budget-skip fixed floor (R2-#1 + round-2 residual):** (a) `GEOMETRY_DIAGNOSTICS_DEADLINE = time.time() + 2.0` (inside the 5 s floor) → `_safe_geometry_diagnostics_inline` returns `passed:null, warnings==["skipped: render budget"]`, no measurement; (b) `... + 3600` → measurement runs normally; (c) with `MCP_RENDER_TIMEOUT_SECONDS` **absent** from `os.environ` (the real production condition), assert (a) and (b) are unchanged — i.e., the skip decision reads ONLY `GEOMETRY_DIAGNOSTICS_DEADLINE` and the fixed `DIAG_BUDGET_FLOOR_SECONDS`, never `MCP_RENDER_TIMEOUT_SECONDS`. Proves the margin can no longer silently collapse to a hardcoded fallback.

**Integration tests — extend `tests/test_mcp_rendering.py`:**
15. **CSV attaches key:** `render_csv_graph` → `status in {ok,warning}`, `geometry_diagnostics` present with `schema_version`, manifest on disk contains `geometry_diagnostics` (mirrors `:306`).
16. **Project attaches key + sidecar location (round1-#33):** `render_project_figure` → `geometry_diagnostics` present, and assert **no** `geometry_diagnostics.json` under `snapshot_project_path` (it lives in `job_root`).
17. **Manifest round-trips (round1-#15/#34):** read `job_root` manifest text back and `json.loads` it — proves numpy/tuple coercion held end-to-end.
18. **Reproducibility unbroken (round1-#33):** re-assert existing provenance checks (`config_sha256`/`environment_sha256` length==64; no fixed pin) — diagnostics entered no hash.
19. **Dry-run stub:** `geometry_diagnostics == {schema_version, passed:null, checks:[], warnings:["dry_run"]}`.
20. **Pre-render / contract-stage error carries the stub (round1-#28; site per R2-#3):** force a missing-column error (CSV contract envelope site `~mcp_surface.py:942`, `failure_stage='CONTRACT'`) and a file-not-found; assert `geometry_diagnostics` is **present** with `passed is None` — distinct from success/dry-run/engine-error.
21. **Warn-only:** overlapping render → `status=="warning"` (never `"error"`), `errors==[]`, figure exists.
22. **Engine-error safety in-frame (round1-#35):** monkeypatch `diagnose_figure_geometry` to raise; assert render still `ok`, `geometry_diagnostics.passed is None`, figure produced (the worker's except at `:85-87` never sees it).
23. **Tri-state discriminator (round1-#30):** assert an agent-style `passed is False` branch behaves correctly across `True`/`False`/`None`.
24. **No-sidecar marker (round1-#32):** simulate a render whose `save_journal_fig` did not run (or env var unset) → response carries `warnings=["geometry_diagnostics_unavailable: ..."]` and `data.reason=="no_sidecar"`, not a silent null.
25. **Env-var no-leak (R2-#2):** after a render returns, assert `GEOMETRY_DIAGNOSTICS_OUT` and `GEOMETRY_DIAGNOSTICS_DEADLINE` are absent from the parent `os.environ` (or restored to their prior values); assert a second in-process render writes to its OWN `job_root`, not the first's.
26. **Schema validity (round1-#26, #16):** assemble the render `outputSchema` (`_standard_output_schema` + per-tool extras) and validate a real response with `jsonschema` (added to test deps). Assert it FAILS before `geometry_diagnostics` is declared and PASSES after — proving additive non-breakage; assert the property is absent from `health`/`list_projects` schemas (per-tool scoping). (If `jsonschema` is rejected as a dep, fall back to a hand-rolled check that required keys are present and no top-level key falls outside the declared set; the test must not be vacuous.)

---

## 10. Open Questions (carried, with disposition)

These are non-blocking calibration/policy items deferred past v1; each has a safe default so implementation can proceed.

- **Q1 — Tick-crowding threshold (0.90) is uncalibrated.** The `TICK_CROWDING_WARN = 0.90` occupancy threshold (§2.2) is a first guess; the true empirical "looks crowded" boundary for FigOps presets is unmeasured. **Default for v1:** ship 0.90 with the `[0.85, 0.95]` `near_boundary` soft band, and flag in the changelog that the `warning` rate is driven mainly by this and `tick_label_overlaps` (§4.3). Recalibrate post-launch against rendered corpora. Does not block.
- **Q2 — Cap the number of reported colliding pairs in `data`.** A pathological figure within the `MAX_TEXT_ARTISTS` cap can still emit a long pair list, bloating the JSON `data`. **Default for v1:** truncate each `*_overlap_pairs` list to the first 50 entries and set `data.<metric>_truncated = true` when truncated. This is a **serialization** fix only — the compute is already bounded by `MAX_TEXT_ARTISTS` (§6) — so it never affects `passed`. Does not block.
- **Q3 — `LC_NUMERIC`/formatter normalization for full cross-platform tick reproducibility (round1-#25).** Whether to force `LC_NUMERIC=C` and pin the tick formatter in the render environment, or to leave the two tick metrics as per-machine-deterministic-only. **Default for v1:** leave unpinned (per-machine deterministic, with `near_boundary` absorbing drift) and document the recommendation to normalize; promote to a hard env normalization only if cross-platform tick warnings prove noisy. Does not block.

---

## 11. Hole resolutions

### 11.1 Round-1 holes (#0–#37 + sidecar-presence) — resolved by the spec above

| # | Reviewer hole (abbrev) | Sev | Resolution |
|---|---|---|---|
| 0 | legend/blank vs data-UNION bbox → false positive over whitespace; ink-mask fix proposed | crit | **DEMOTE** `legend_data_collision` and `blank_area_ratio` to **info-only** (report number, never flip status; explicitly labeled bbox-union approximation). **REJECT** ink-mask rasterization — font/platform-nondeterministic, violates determinism constraint. §2.5/§2.8. |
| 1 | rotated tick labels → AABB false-positives overlap+crowding; §8 "no special case" | high | **FIX**: along-axis **projected** spacing/length for `get_rotation()%180!=0`. Remove §8 "no special case". §2.1/§2.2/§8. |
| 2 | `artists_outside_axes` fires on intentional zoom | high | **FIX**: gate on `get_autoscalex_on()/y True AND overflow`; skip when limits explicit. §2.3. |
| 3 | empty axes → false 100%-outside (inf sentinel transformed before skip) | high | **FIX**: finite/sentinel/no-artist guard **before** any `transform_bbox`. §2.3 step 1. |
| 4 | `dataLim` ignores `set_visible(False)` → inflated extent | med | **FIX**: data extent from visible artists only, never raw `dataLim`. §2.0/§2.3. |
| 5 | transparent/invisible artists reported as present | med | **FIX**: universal `get_visible()`+`alpha>ALPHA_EPS` filter; §8 reversed. §2.0/§8. |
| 6 | annotation-vs-marker false negative (zero-area offsets) | med | **FIX**: expand to marker footprint via `get_sizes()`. §2.9. |
| 7 | colorbar classified by elimination → confused with twinx/inset | med | **FIX**: positive tag `_graph_hub_role='colorbar'` at `bridge_renderer.py:650-652`. §2.7/§3.5. |
| 8 | project path has no in-engine live-figure hook | crit | **FIX (architecture)**: hook in `save_journal_fig` (reached by scaffolded scripts, `scaffold.py:94/:149`) + env-var sidecar. §3.2. |
| 9 | `layout_locked` source undefined; common case unlocked | high | **FIX**: compute `getattr(fig,'_graph_hub_layout_lock',None) is not None` at the hook. §2.4/§3.3. |
| 10 | hook ordering correct for only 1 of 3 CSV branches | high | **MOOT**: hook is downstream of all layout (in `save_journal_fig`); `data_axes` derived from visible `fig.axes`. §3.2/§3.4. |
| 11 | diagnostics must run after layout/draw | high | **MOOT** by post-primary-save hook; renderer current/forced-once. §3.2. |
| 12 | mixed coordinate frames (dataLim vs ink extents) | med | **FIX/STATE**: §2.3 explicitly value-based (states what it does NOT catch); §2.9 uses ink-inclusive footprints. §2.3/§2.9. |
| 13 | Queue transport described doesn't exist; return-contract surgery | med | **MOOT**: sidecar transport via env var; Queue untouched; worker `str` return unchanged. §3.2. |
| 14 | (same as #4, dataLim visibility) | med | **FIX** with #4. §2.0. |
| 15 | numpy scalars crash manifest `json.dumps` (no `default=str`) | crit | **FIX**: native-type coercion at source (post-condition + test). §2.0/§9.2. |
| 16 | `Bbox.intersection` None / zero-area undefined | high | **FIX**: exact None-safe, area-guarded predicate. §2.0. |
| 17 | absolute-pixel overlap scales with `fig.dpi` (contradicts invariance) | high | **FIX**: fraction-of-smaller-box thresholds; `GEOM_EPS_PX` only a sub-pixel floor. §2.0/§5. |
| 18 | Queue must pickle dict; unpicklable leak hangs worker | med | **FIX/MOOT**: pure-JSON post-condition (#15) + sidecar replaces Queue. §2.0/§3.2. |
| 19 | O(n²)/per-marker blow-up in §2.5/§2.9 | high | **FIX**: aggregate `dataLim` targets (O(1)); `MAX_TEXT_ARTISTS` cap; sweep not O(n²). §2.0/§2.5/§2.9. |
| 20 | tuples don't survive JSON; tests assume they do | med | **FIX**: pairs are `list[list[int]]` everywhere; tests assert lists. §2.0/§4.1/§9.2. |
| 21 | extra pre-save draw blows 120s → worker killed → artifact lost | crit | **FIX**: hook **after** primary `savefig` (artifact durable) + v1 wall-clock guard. §3.2/§6. |
| 22 | §2.9 unbounded O(n)+O(n²) annotations | high | **FIX**: `MAX_TEXT_ARTISTS=200` skip before any pairwise work. §2.0/§2.9. |
| 23 | §6 "100k==100" false for draw; always-on no gate | high | **FIX**: post-save reuses renderer (no draw on PNG primary); wall-clock guard ships v1; correct the §6 claim. §6. |
| 24 | multipanel multiplies cost ×N panels | med | **FIX**: single aggregate budget across panels; partial-skip on over-budget. §6/§3.2. |
| 25 | no `schema_version` | high | **FIX**: required `schema_version="geometry_diagnostics/1"` + bump policy. §4.1/§4.3. |
| 26 | `checks`/`data` untyped in outputSchema | high | **FIX**: typed item with `name` enum + required keys; `data` declared advisory-untyped. §4.2/§4.3. |
| 27 | `geometry_diagnostics` sometimes-present on pre-render errors | high | **FIX**: stub at **every** return site incl. contract-stage errors; integration test §9.20. §3.2/§9.20. |
| 28 | declaring in `_standard_output_schema` pollutes ~11 tools | med | **FIX**: declare in per-tool extras `:273-284`/`:306-322` only. §4.2. |
| 29 | ok→warning flip presented as no-op | med | **STATE**: declared behavioral change; routed only through existing `manual_review_needed`; changelog warning-rate note. §4.3/§7. |
| 30 | additive-safety claim falsified by undeclared `calculation_checks` | low | **FIX**: declare `calculation_checks` too, making strict-validator claim true. §4.2/§4.3. |
| 31 | tri-state `passed` footgun (`if not passed:`) | low | **STATE+TEST**: document `passed is False`/`is None`; test §9.23. §4.3/§7. |
| 32 | project diagnostics structurally unobtainable (user script bypasses bridge) | crit | **FIX**: same as #8 — `save_journal_fig` chokepoint reaches all scaffolded/legacy scripts that route through it; `no_sidecar` stub covers the rest. §3.2. |
| 33 | numpy scalars hard-fail response in parent (post-success) | crit | **FIX**: native coercion (#15) + manifest round-trip test §9.17. §2.0/§9.17. |
| 34 | safe wrapper at wrong process layer → worker still hard-fails | crit | **FIX**: try/except in-frame inside `save_journal_fig`; parent never raises on null. §3.3/§9.22. |
| 35 | Test boundary font-dependent knife-edge | high | **FIX**: boundary tested on synthetic `Bbox` math; font tests far from threshold. §9.4. |
| 36 | Test assumes nonexistent outputSchema validator | med | **FIX**: add `jsonschema` to test deps (or hand-rolled non-vacuous check); assert fail-before/pass-after. §9.26. |
| 37 | tick filter by `get_text()` drops labels / mis-pairs adjacency; ignores offset text | low | **FIX**: adjacency by spatial position; offset text stated out-of-scope. §2.1/§8. |
| — | project sidecar presence varies by script vintage (no_sidecar) | med | **FIX**: distinct `no_sidecar` stub + warning; kept out of every hash. §3.2/§5/§9.24. |

### 11.2 Round-2 holes (R1–R7) — these critique the round-1 SPEC itself

| R# | Reviewer hole (abbrev) | Sev | Resolution |
|---|---|---|---|
| R1 | Wall-clock budget guard ships v1 but start-time/deadline transport into `save_journal_fig` is unspecified; child/subprocess cannot know the parent's deadline | crit | **FIX**: parallel env var `GEOMETRY_DIAGNOSTICS_DEADLINE = time.time() + MCP_RENDER_TIMEOUT_SECONDS` (absolute **epoch**, not monotonic — cross-process comparable), set at the SAME CSV/project sites as `GEOMETRY_DIAGNOSTICS_OUT`; the child compares `deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS` (a **fixed 5 s floor**) and stubs `passed:null` if under-floor. **The total budget is NOT used to size the margin and `MCP_RENDER_TIMEOUT_SECONDS` is never read from `os.environ` (it is a module constant, `:61`) — the round-2 residual was a percentage margin that silently collapsed to its fallback; a fixed floor removes the dependency since the diagnostics pass is hard-bounded and sub-second.** Verified to reach both spawn (CSV) and subprocess (project). Replaces the round-1 `elapsed > 0.7*timeout` phrasing (child has no start time). §3.2 "Wall-clock budget transport" + §6 + §9.14. |
| R2 | CSV env-var transport (T4) mutates parent `os.environ` and never cleans up → stale value redirects the next in-process save's sidecar | high | **FIX**: set+remove BOTH `GEOMETRY_DIAGNOSTICS_OUT` and `GEOMETRY_DIAGNOSTICS_DEADLINE` in a `try/finally` around the render dispatch (restore prior value or pop). One mechanism covers both vars so closing R2 cannot reopen under the deadline var. Chosen over `spec_payload` threading because it covers CSV and project identically and needs no new frozen-dataclass field. `call_tool` is sync → no interleave race. §3.2 "Env-var cleanup" + §9.25. |
| R3 | T6 contract-stage geometry-stub injection cites `:3486-3504` inside `_validate_render_data_contract` (a validation helper) — that dict never becomes the MCP response; test #19 would still fail | high | **FIX**: retarget the contract-error stub injection to the **real envelope site ~`mcp_surface.py:942`** (`if contract_errors:` block, `status='error'`, `failure_stage='CONTRACT'`) — where `calculation_checks` already reaches the envelope. §11.3 T6 + §9.20. |
| R4 | T5 (project transport) doesn't flag that `_run_project_figure_script` lacks `job_root` in scope (receives `snapshot_project_path`), unlike T4 which flags its threading need | med | **FIX**: T5 now explicitly derives `job_root = snapshot_project_path.parent` (or threads `job_root` into the function) before building the sidecar/deadline env entries. §11.3 T5. |
| R5 | T4 sidecar-read placement imprecise: `_run_render_bridge_figure` is a `@staticmethod` returning `None`; the parent-side sidecar read cannot live there | med | **FIX**: T4 now places the sidecar read + `no_sidecar` stub-fallback in the **CSV tool body (~`mcp_surface.py:1021-1034`)** where `job_root`/`output_path` are in scope, NOT in the static worker method (which only sets the env var pre-`start()` and reads the queue result). §11.3 T4. |
| R6 | "reaches the entire installed base of legacy/scaffolded scripts" over-claims the chokepoint; an arbitrary user script can `fig.savefig` directly and bypass `save_journal_fig` | low | **FIX (soften)**: scope reworded to "all scripts that **route through** `save_journal_fig`" (scaffolded + CSV bridge); bypassing scripts degrade to the `no_sidecar` stub. §3.2 "Chokepoint scope is bounded" + §8. |
| R7 | Native-type post-condition rationale imprecise: the sidecar JSON boundary already blocks numpy from the parent, so the "numpy TypeErrors in the parent after success" framing is wrong (applies only to in-parent inlining) | low | **FIX (rationale only, requirement stands)**: corrected §2.0 to state the real job is making the CHILD's `json.dumps(diag)` write succeed (else it degrades to the stub); `json.loads` of the sidecar yields only native types so the parent's manifest dumps cannot TypeError on diagnostics. §2.0 "Native-type post-condition". |

---

### 11.3 Round-2 residual holes (final verifier, post-workflow) — resolved

| # | Residual hole (abbrev) | Sev | Resolution |
|---|---|---|---|
| RR1 | Budget margin silently broken: `MCP_RENDER_TIMEOUT_SECONDS` is a module constant (`mcp_surface.py:61`), never in `os.environ`, so the child's `os.environ.get(...)` always missed and the intended `0.3×120=36 s` margin collapsed to a hardcoded 5 s. | high | **FIX**: drop the percentage margin entirely. The child skips iff `deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS` (**fixed 5 s**), needing only the already-transported absolute `GEOMETRY_DIAGNOSTICS_DEADLINE`. `MCP_RENDER_TIMEOUT_SECONDS` is never read from env. Safe because the diagnostics pass is hard-bounded (`MAX_TEXT_ARTISTS` cap, O(1) marker boxes, neighbor-sweep) and sub-second, so a constant headroom suffices regardless of total budget. §3.2/§3.3/§9.14/§11.3-T3. |
| RR2 | Rotated tick-label "along-axis projected glyph length" had no formula — an unmade geometry decision (which projection? `w·cosθ+h·sinθ` vs rotated-corner vs measure-then-rotate). | med | **FIX**: define it once in §2.0 as the `get_window_extent` AABB extent in the axis direction (`bb.width` for x, `bb.height` for y). `get_window_extent` already returns the rendered, **rotated** text's bbox, so this extent **is** the exact axis-direction footprint (≡ `w·|cosθ|+h·|sinθ|` for x) — no trig is chosen by the implementer. Also corrects the prior "AABB width is the diagonal" misconception. §2.0/§2.1/§2.2. |

---

## 12. Implementation plan (ordered; exact edit sites — no production code written here)

> Hand-off contract for the implementer. Each task lists the file, the function/line anchor from the grounding, and the change. Do all schema/envelope/transport/cleanup wiring in `mcp_surface.py`; do the measurement in the new pure module; do the single hook in `journal_theme.py`; add one positive tag in `bridge_renderer.py`.

**T1 — New pure module `hub_core/geometry_diagnostics.py` (mirrors `hub_core/figure_preflight.py`).**
- New file. Module-level constants (`SCHEMA_VERSION`, `GEOM_EPS_PX`, `ALPHA_EPS`, `MAX_TEXT_ARTISTS`, the four `*_WARN`).
- `def diagnose_figure_geometry(fig, data_axes, *, layout_locked) -> dict` implementing all nine §2 metrics with §2.0 predicates/filters/caps.
- **Import constraint:** matplotlib only; import nothing from `themes/` or `hub_core/` (cycle: `themes/style_packs.py:7` already imports `hub_core`).
- Post-condition: pure-JSON tree (native types, list-of-list pairs).

**T2 — Positive colorbar tag.** `plotting/bridge_renderer.py:650-652`, `_render_heatmap_plot`, immediately after `colorbar = ax.figure.colorbar(mesh, ax=ax)`: add `colorbar.ax._graph_hub_role = "colorbar"`.

**T3 — The single live-figure hook + in-frame safe wrapper + budget read.** `themes/journal_theme.py`, inside `save_journal_fig` (def at `:397`), **after the primary `fig.savefig(filename, metadata=metadata, **kwargs)` at `:445`** and before the PDF companions at `:452-458`:
- Add the function-local helper `_safe_geometry_diagnostics_inline(fig)` (§3.3): function-local `from hub_core.geometry_diagnostics import diagnose_figure_geometry, SCHEMA_VERSION` (cycle avoidance); read `GEOMETRY_DIAGNOSTICS_DEADLINE` only and apply the **fixed-floor** budget skip (`deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS = 5.0`; do **NOT** read `MCP_RENDER_TIMEOUT_SECONDS` — it is a module constant at `mcp_surface.py:61`, never in `os.environ`) (R2-#1 + round-2 residual); derive `data_axes` (visible, non-colorbar `fig.axes`) and `layout_locked` from `getattr(fig, _LAYOUT_LOCK_ATTR, None) is not None` (`_LAYOUT_LOCK_ATTR` at `:46`).
- Read `os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")`; if set, run the helper and `Path(out).write_text(json.dumps(diag))` inside its own try/except (writing must never fail the save).
- Ensure `import json/os/time` at function scope (or module top if already present).

**T4 — CSV transport: set env (parent), in-frame deadline, sidecar read in TOOL BODY (R2-#1, R2-#2, R2-#5).**
- **Env set + cleanup (parent, CSV tool body around `:1021-1034`, where `job_root` is in scope):** in a `try/finally` around the `_run_render_bridge_figure` dispatch, set `os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = str(job_root / "geometry_diagnostics.json")` and `os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + MCP_RENDER_TIMEOUT_SECONDS)`; in `finally`, restore/pop both. No Queue change; `_run_render_bridge_figure` (the `@staticmethod` at `:1621`) stays as-is (still returns the queue result, no `job_root` param needed for transport).
- **Sidecar read (CSV tool body, NOT the staticmethod — R2-#5):** after the worker result is read, load `job_root/geometry_diagnostics.json` into a `geometry_diagnostics` dict; on missing/unreadable → `no_sidecar` stub (§3.2). This is where `job_root`/`output_path` are in scope.

**T5 — Project transport: derive `job_root`, set env-dict entries, sidecar read (R2-#1, R2-#2, R2-#4).** `hub_core/mcp_surface.py`, `_run_project_figure_script` (`:1894-1931`):
- **Derive `job_root` (R2-#4):** the function receives `snapshot_project_path`, not `job_root`; compute `job_root = snapshot_project_path.parent` (or thread `job_root` through the signature). Required because the sidecar must land OUTSIDE the snapshot (round1-#33).
- Add to the `env` dict already built at `:1911-1919`: `"GEOMETRY_DIAGNOSTICS_OUT": str(job_root / "geometry_diagnostics.json")` and `"GEOMETRY_DIAGNOSTICS_DEADLINE": str(time.time() + MCP_RENDER_TIMEOUT_SECONDS)`. (The per-subprocess `env=os.environ.copy()` derivation is race-free for the child; the parent leak is handled by the CSV-side `try/finally` pattern and an analogous `finally` if this path also touches `os.environ` — here it uses a local env dict, so no parent mutation occurs and no cleanup is needed for the subprocess path.)
- After `subprocess.run` returns, read the sidecar at the caller where `job_root` is available; missing → `no_sidecar` stub.

**T6 — Envelope merge (CSV); contract-error stub at the REAL envelope site (R2-#3).** `hub_core/mcp_surface.py`:
- Add `geometry_diagnostics=<dict>` as an `_envelope` kwarg at the CSV success (`:1161-1186`), dry_run (`:957-981`), error (`:810-1159`), AND the **contract-stage early-error envelope at ~`:942`** (the `if contract_errors:` block, `status='error'`, `failure_stage='CONTRACT'`) — NOT inside `_validate_render_data_contract` (`:3471/:3486-3504`), whose dict never becomes the response. Dry-run/pre-render use the appropriate stub (`dry_run` / `no figure` reasons).
- Manifest embed: add `manifest["geometry_diagnostics"] = <dict>` parallel to the `visual_preflight_status` embed at `:1081`.
- New flattener `_geometry_warnings(diag)` (mirror `_preflight_warnings` at `:2765-2777`): pull `warnings` + `detail` of warning-eligible failed checks into the response `warnings` list.
- Fold into `manual_review_needed` at `:1051-1057`: `... or bool(geometry_warnings)`.

**T7 — Envelope merge (project).** `hub_core/mcp_surface.py`: same as T6 at the project success (`:1481-1512`), dry_run (`:1269-1293`), error (`:1451-1479`) sites; manifest embed parallel to `:1387`. (Project has its own contract/early-error envelope sites — apply the stub there too, by analogy with the CSV `~:942` site.)

**T8 — outputSchema (per-tool extras only).** `hub_core/mcp_surface.py`:
- Add the typed `geometry_diagnostics` property (§4.2, with `name` enum) to the render_csv_graph extras dict at `:273-284` AND the render_project_figure extras dict at `:306-322`.
- In the same change, add `"calculation_checks": {"type": "object"}` (or array) to the CSV extras at `:273-284` to close the pre-existing strict-validation gap (round1-#30).
- Do **not** modify `_standard_output_schema` (`:131-152`).

**T9 — Tests.**
- New `tests/test_geometry_diagnostics.py` — unit tests §9.1-14 (incl. the synthetic-`Bbox` boundary test §9.4, the `json.dumps` post-condition §9.2, and the budget-skip stub §9.14). `unittest.TestCase`.
- Extend `tests/test_mcp_rendering.py` — integration tests §9.15-26 (CSV/project key attach, sidecar-not-in-snapshot, manifest round-trip, reproducibility, dry-run, contract-stage-error stub at the real envelope, warn-only, in-frame engine-error safety, tri-state, no_sidecar, **env-var no-leak §9.25**, schema validity).
- If §9.26 uses `jsonschema`, add it to the test/dev deps in `pyproject.toml` (`[tool.pytest.ini_options]` at `:43-46`); otherwise implement the hand-rolled non-vacuous check.

**T10 — Docs/changelog.** Note in the changelog (and `AGENTS.md`/`README.md` render-tool docs): geometry diagnostics intentionally raise the `warning` rate; the `schema_version`/bump policy; the tri-state `passed` consumption rule; the two new env vars (`GEOMETRY_DIAGNOSTICS_OUT`, `GEOMETRY_DIAGNOSTICS_DEADLINE`) and that they are render-scoped (set/cleared per render); the `LC_NUMERIC`/formatter normalization recommendation for the two tick metrics; and the §10 open questions.

**Ordering:** T1 → T2 → T3 (measurement + hook + budget read, testable via T9 units) → T4/T5 (transport + cleanup + sidecar read) → T6/T7 (envelope + contract stub) → T8 (schema) → T9 (integration) → T10. T2 and T8 are one-line/declarative and may land first to de-risk.
