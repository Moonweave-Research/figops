# License And Distribution Decision - 2026-06-09

## Decision

FigOps remains private and proprietary for now.

The repository uses an all-rights-reserved license notice. No open source
license is granted at this stage.

## Rationale

FigOps is not just a plotting helper collection. Its value is in the
combined operating system:

- `project_config.yaml` figure contracts;
- MCP tool surface;
- runtime snapshot rendering;
- style consistency and publication presets;
- visual preflight and artifact QA;
- provenance and reproducibility hooks;
- project normalization and scaffold workflows.

Publishing the full repository under a permissive license too early would expose
the operating model before the intended public surface is separated from private
research workflows.

## Current Policy

- Keep the full FigOps repository private.
- Treat current source, docs, style contracts, project templates, and MCP code as
  internal Moonweave Research assets.
- Do not distribute code or derived packages externally unless a separate license
  decision is made.
- Keep real research project paths, style presets, and workflow documents out of
  any future public edition unless explicitly reviewed.

## Future Public Release Options

### Option A: Apache-2.0 Public Core

Use if the goal is broad adoption, citation, and commercial-compatible reuse.

Good candidates for a public core:

- MCP protocol surface;
- generic project config schema;
- synthetic example fixtures;
- generic style templates;
- runtime snapshot runner;
- basic preflight checks.

Keep private:

- project-specific research presets;
- unpublished research workflow documents;
- real data paths and project-specific configs;
- internal HKS notes that encode lab operating practice.

### Option B: Source-Available Research License

Use if the goal is transparency and academic reuse while limiting commercial
productization.

This would not be OSI open source. It may reduce industry adoption, but it can
better protect a research-tool business or lab platform direction.

### Option C: Keep Private

Use while the tool remains a competitive research workflow asset or while the
public surface is not yet separated.

This is the current decision.

## Review Trigger

Revisit this decision when one of these becomes true:

- a public `graphhub-lite` package is split from the private repository;
- an external collaborator needs formal reuse rights;
- the repository is prepared for public GitHub release;
- FigOps becomes part of a paper, demo, or product-facing distribution.

## Required Release Checklist

Before any public release:

- [ ] Remove real research project paths and private workflow references.
- [ ] Replace private examples with synthetic fixtures.
- [ ] Decide between Apache-2.0, a source-available research license, or another
      reviewed license.
- [ ] Add dependency license review.
- [ ] Add README license summary.
- [ ] Verify `LICENSE` and `NOTICE` match the intended distribution mode.
