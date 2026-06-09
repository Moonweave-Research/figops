# Graph Hub Productization Hardening Spec - 2026-06-09

## Goal

Prepare Graph Hub for a future public or commercial release without exposing private research workflow value by accident.

This is not a decision to open source the repository. The current license remains proprietary and all-rights-reserved. This spec adds the boundaries and checks needed before any future public edition can be split.

## Product Boundary

### Public-Core Candidates

These components can eventually move into a public `graphhub-core` or `graphhub-lite` edition after review:

- MCP protocol surface and JSON-RPC framing;
- generic `project_config.yaml` schema;
- synthetic fixture projects;
- runtime snapshot rendering;
- basic CSV graph rendering;
- generic journal target formats such as `nature`, `science`, `acs`, `rsc`, `elsevier`, `wiley`, and `cell`;
- basic preflight and artifact manifest structure.

### Private/Internal Candidates

These must stay private unless explicitly reviewed:

- real project configs and paths;
- lab-specific HKS workflow notes;
- `nature_surfur` and other project-derived style presets;
- tuned QA thresholds derived from unpublished work;
- private agent workflow documents;
- hosted runtime deployment details.

## Style Pack Architecture

Graph Hub should treat visual style as named packs, not ad hoc prompt text.

Each style pack has:

- `name`
- `visibility`: `public_core`, `internal`, or `private`
- `target_formats`
- `profiles`
- `release_note`

Rules:

- `graphhub.list_styles` must expose style pack metadata so agents know which styles are generic and which are private.
- `nature_surfur` is internal because it is project-derived.
- `baseline` profile is public-core.
- `resistance_premium` is internal because it originated from resistance publication styling.

## Release Safety Check

Add a read-only release check script:

```bash
python scripts/check_public_release.py
```

The script must fail a public release if it sees:

- all-rights-reserved `LICENSE`;
- `NOTICE` saying no open source license is granted;
- private or internal style packs;
- known private path markers such as `02_Surfur_Polymer`, `PI_control`, or `저항 측정`;
- internal HKS documents;
- real project identifiers in public docs.

This check is intentionally conservative. It is a release gate, not a normal development gate.

## Gold Smoke Expansion

Current gold smoke:

- CSV graph render;
- `02_Surfur_Polymer/저항 측정/PI_control` `FigPI_CvS_Fits` project figure render.

Next gold targets:

1. A synthetic public fixture project.
2. A multi-panel publication-style fixture.
3. A failure UX fixture with a missing column and clear resolution hint.

## MCP Error UX Checklist

Every user-facing MCP failure should include:

- `failure_stage`;
- sanitized error text;
- `resolution_hint`;
- `manual_review_needed`;
- no raw private absolute path leakage unless the user explicitly provided the path.

## Implementation Plan

### Task 1: Style Pack Registry

- Create `themes/style_packs.py`.
- Classify current target formats and profiles by release visibility.
- Add tests that `nature_surfur` and `resistance_premium` are not public-core.
- Expose `style_packs` from `graphhub.list_styles`.

### Task 2: Public Release Check

- Create `scripts/check_public_release.py`.
- Add tests for all-rights-reserved license blocking, private markers, and internal style packs.
- Keep the script read-only.

### Task 3: Gold Smoke Expansion

- Keep the real PI_control smoke as internal proof.
- Add synthetic fixture smoke before any public release.
- Add multi-panel fixture after style pack split is stable.

### Task 4: Error UX Audit

- Audit `render_csv_graph` and `render_project_figure` failures.
- Add missing-column and bad-style tests if gaps remain.

## Acceptance Criteria

This pass is complete when:

- style pack metadata exists and is returned by `graphhub.list_styles`;
- public release check blocks the current private repo;
- tests cover style pack classification and release check behavior;
- docs state what can be public and what stays private;
- no current work attempts to open source or relicense the repository.

## Current Decision

Proceed with productization hardening while keeping Graph Hub private and proprietary.
