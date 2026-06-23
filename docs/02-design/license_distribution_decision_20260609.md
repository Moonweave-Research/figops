# License And Distribution Decision - 2026-06-09

## Decision

Graph Making Hub's public-core source tree is licensed under the Mozilla Public
License 2.0 (MPL-2.0).

This decision applies to the public-core repository contents only. It does not
grant rights to private datasets, unpublished workflow notes, credentials,
manuscript assets, internal style packs, or project-specific research material
unless those assets are explicitly included with their own notices.

## Rationale

Graph Making Hub is not just a plotting helper collection. Its value is in the
combined operating system:

- `project_config.yaml` figure contracts;
- MCP tool surface;
- runtime snapshot rendering;
- style consistency and publication presets;
- visual preflight and artifact QA;
- provenance and reproducibility hooks;
- project normalization and scaffold workflows.

Publishing the public core under MPL-2.0 supports reusable FigOps tooling while
keeping project-specific research assets and internal workflow material outside
the public distribution boundary.

## Current Policy

- License the public-core source under MPL-2.0; see `LICENSE` and `NOTICE`.
- Keep private datasets, unpublished workflow notes, credentials, manuscript
  assets, internal style packs, and project-specific research material out of the
  public-core tree unless explicitly reviewed and noticed.
- Do not treat access to excluded private material as part of the MPL-2.0 grant.
- Keep remote visibility changes, package publication, registry publication, and
  any history rewrite as separate human-gated actions.

## Future Public Release Options

### Public Core

Included public-core candidates:

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
- internal operating notes that encode lab-specific practice.

### Excluded Private Material

Excluded material stays outside the public-core grant unless later reviewed and
included with explicit notices:

- real research data and project paths;
- project-specific presets and internal style packs;
- unpublished manuscript assets;
- private workflow notes and local operating playbooks;
- credentials, tokens, caches, and runtime state.

## Review Trigger

Revisit this decision when one of these becomes true:

- an external collaborator needs formal reuse rights;
- the public-core boundary expands to include new asset classes;
- Graph Hub becomes part of a paper, demo, or product-facing distribution.

## Required Release Checklist

Before any public release, visibility change, package publication, or registry
publication:

- [x] Remove real research project paths and private workflow references from the
      public-core tree.
- [x] Replace private examples with synthetic fixtures or public-safe examples.
- [x] Apply MPL-2.0 metadata in `LICENSE`, `NOTICE`, README, and package
      metadata.
- [ ] Add dependency license review.
- [x] Add README license summary.
- [x] Verify `LICENSE` and `NOTICE` match the intended distribution mode.
