# M5 — DX, docs, shareability — implementer spec

> Goal (`docs/ROADMAP.md`): a new lab member or collaborator goes clone → first figure in minutes,
> and the API is self-describing for humans **and** LLM agents (DX 4→8). This is what makes the tool
> genuinely *shareable*. **Depends on M3.2** (registry) for discovery. Design/acceptance level.

## M5.1 — Capabilities / discovery API — S

**Problem (today):** an LLM caller can't discover valid `plot_type` values via the API — `list_styles`
returns formats/profiles but not plot types or their per-type args. Enums were added for
format/profile (PR #55) but plot-type discovery is still thin.

**Design:** a `figops.describe` tool (or an enriched `list_styles`) that returns, from the M3.2
registry + the tool registry (`docs/architecture.md`):
- every plot type with its `arg_schema` + `capabilities` (supports_series/yerr/broken_axis/...),
- every tool with its input/output schema and a one-line purpose,
- the available data-contract semantic checks,
- a worked example per plot type.

One source (the registries) feeds `tools/list`, the RPC validator, **and** `describe` — no drift.

**Acceptance:** an agent can call `describe`, learn every capability + argument, and render a figure
**without trial-and-error**; `describe` output is generated from the registries (not hand-maintained).

## M5.2 — Docs set — M

Create under `docs/`:
- **Quickstart** (`docs/quickstart.md`): clone → `uv sync` → scaffold → render a figure from a CSV,
  in <10 minutes, zero bespoke env (relies on M3 adapter defaults).
- **Tool reference** (`docs/tools.md`): **auto-generated** from the tool inputSchemas (a small script
  in `scripts/` that renders the registry to markdown; run in CI to keep it fresh).
- **Worked examples** (`examples/`): the existing `examples/{multipanel,synthetic}_project` extended
  with commentary + expected outputs, runnable as a tutorial.
- **Contributor guide** (`CONTRIBUTING.md`): architecture (link `docs/architecture.md`), how to add a
  plot type (register one `PlotType`), how to add a tool, the TDD + review-until-clean workflow, CI.
- **Env trust model**: finalize (started PR #55 in `AGENTS.md`) as a security doc.
- **"New lab member" path**: a one-page onboarding linking the above.

**Acceptance:** a person who has never seen the repo follows the quickstart to a rendered figure; the
tool reference is regenerated in CI and matches the live schemas.

## M5.3 — Self-check / doctor — S

**Design:** extend the existing `figops_mcp_server.py --smoke` into a `graphhub doctor` that
validates the environment and reports readiness: Python/uv, optional `[io]` deps, `Rscript`
availability, write-tool gating state, resolved roots + any broad-root warnings (PR #55),
adapter selection (M3.1). Human-readable + a `--json` mode for agents.

**Acceptance:** `doctor` clearly reports what's installed/configured and what's missing, with
actionable hints; it's the friendly front door for a new user diagnosing setup.

## M5.4 — Release discipline — S

**Design:** adopt semver for the package (`pyproject.toml` version), maintain a `CHANGELOG.md`
(Keep a Changelog style), and tag releases. Prereqs for sharing the tool with others.

**Acceptance:** `CHANGELOG.md` exists and is updated per feature PR; a tagged release exists;
version bumps are deliberate.

## Definition of done (M5)

- `describe` lists every capability from the registries; agents render without guessing.
- Quickstart verified clone→figure (CI smoke); tool reference auto-generated + CI-checked.
- `doctor` reports readiness; CHANGELOG + tags in place.
- The tool is genuinely handoff-able: a new collaborator can install, learn, and produce a figure
  from the docs alone.
