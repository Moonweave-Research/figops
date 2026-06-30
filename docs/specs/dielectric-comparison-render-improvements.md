# FigOps Dielectric-Comparison Render Improvements

Status: implemented for `render_csv_graph` in this PR.
Scope: three improvements to `render_csv_graph` surfaced by a real report build.

## 0. Motivation

A PNU LCE dielectric report needed an apples-to-apples ε′/ε″ comparison of our swept-frequency data against a published reference (White et al., *J. Mater. Chem. C* 2026, Fig. 1e — ε′ on the left axis, ε″ on the right axis, vs frequency). Building the FigOps side of that comparison hit three friction points. Items 1–3 below are each a recurring "fallback-to-matplotlib / workaround" reason, which is the promotion criterion in `polish-layer-adversarial-roadmap.md`.

The implemented API is intentionally narrow and backward-compatible.

## 1. Secondary (twin) y-axis for `render_csv_graph`

- **Problem.** A single graph exposes only one y-axis (`y_column`, `y_scale`, `y_axis_label`). There is no way to put two y-quantities on a shared x with independent left/right axes. The reference figure uses ε′ (left) and ε″ (right) over a shared log-frequency x; we could only stack both quantities on one log y-axis, which is not the reference's format.
- **Use case.** Dielectric spectra (ε′ left, ε″ right), and any dual-quantity-vs-x figure where the two quantities have different ranges/scales.
- **Implemented.** Opt-in `secondary_y` object with `column`, optional `axis_label`, `scale`, `series_label`, and `limits`. Render via `ax.twinx()`. The legend merges handles from both axes into a single legend.
- **Code pointers.** Schema/handler: `hub_core/mcp/tools/render_csv.py`. Rendering: `plotting/bridge_renderer.py` (and `plotting/renderers/`).
- **Acceptance.** MCP schema → normalization → `twinx` render → merged single legend → secondary log-scale data-contract validation → generated docs updated.
- **Deferred.** Per-series primary/secondary axis assignment remains out of scope; the shipped shape covers one primary y column plus one secondary y column.

## 2. Line plots should not force per-point markers

- **Problem.** `plot_type: "line"` renders a marker at every data point. With hundreds of swept-frequency points the markers merge and visually thicken/obscure the line. Workaround was per-series `series_styles: { <label>: { marker: "none" } }`.
- **Implemented.** For line-style rendering, default to no per-point markers. Markers remain opt-in via `series_styles[...].marker`. Scatter behavior is unchanged.
- **Code pointers.** Marker sizing/tokens: `plotting/renderers/figure_style.py` (`marker_tokens`), consumed in `plotting/bridge_renderer.py`; the line draw path.
- **Acceptance.** A dense single-series and multi-series line render is clean (no marker blobbing) by default; markers remain available opt-in; pixel/fixture evidence for both default and opt-in.

## 3. Default title leak ("FigOps MCP render")

- **Problem.** When `title` is omitted, the rendered artifact bakes the placeholder string **"FigOps MCP render"** into the figure. Suppressing it required passing `title: " "`.
- **Code pointer.** `hub_core/mcp/tools/render_csv.py` — the `str(arguments.get("title") or "FigOps MCP render")` fallback (≈ line 506 on `main`).
- **Implemented.** When no `title` is provided (absent or empty), render no title at all; never bake a placeholder. An explicitly provided `title` is honored unchanged.
- **Acceptance.** No `title` key → no title text in the artifact; `title: ""` → no title; explicit non-empty `title` → rendered as given.
