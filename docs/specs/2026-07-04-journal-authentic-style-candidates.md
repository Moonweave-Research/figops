# Journal Authentic Style Candidate Layer

Date: 2026-07-04

This spec defines the FigOps candidate layer for authentic journal-track visual language. It separates existing hard render floors from non-default visual-feel candidates. Candidate metadata is evidence for review and future experimentation only; it is not a publisher rule, not a latest-compliance claim, and not enough for a publication-ready verdict.

## Contract

`themes.authentic_style_language.get_authentic_style_candidate_deltas(target_format: str)` returns:

```json
{
  "schema_version": "authentic_style_candidate_deltas/1",
  "target_format": "science",
  "candidate_deltas": [],
  "descriptive_observations": [],
  "official_claim": false
}
```

Each `candidate_deltas` entry has exactly these fields:

- `token`: existing render token name.
- `current_value`: value from `get_render_style_tokens(target_format, "baseline")`.
- `candidate_value`: explicit measurable candidate value.
- `delta_kind`: measurable change class such as `increase_pt`, `decrease_pt`, or `decrease_fraction`.
- `rationale_category`: one of `observed_visual_language` or `heuristic_publication_convention` for this first wave.
- `source_note`: dated source note beginning with `2026-07-04`.
- `claim_boundary`: non-official, non-default candidate boundary.
- `apply_by_default`: always `false`.

`descriptive_observations` are copied from the dated visual-language matrix. They describe a journal track but do not force a token delta. Tracks may have observations and zero candidate deltas.

Style-delta and render-pack summary JSON expose this helper payload under the explicit per-track key `authentic_style_candidates`. The first-wave schema does not define a `candidate_metadata` alias; consumers should read `track_deltas[].authentic_style_candidates`.

## Boundaries

Allowed rationale categories across the wider journal evidence model are:

- `official_submission_constraint`
- `encoded_figops_token`
- `observed_visual_language`
- `heuristic_publication_convention`
- `unsupported_or_deferred`

Candidate deltas in this wave do not use `official_submission_constraint`, because they are not publisher requirements. They also do not use `encoded_figops_token`, because defaults already live in `get_render_style_tokens()`. Inaccessible, unverifiable, or not-yet-measurable claims remain `unsupported_or_deferred` in the matrix, not candidate deltas.

## Track Notes

Current candidate metadata is intentionally conservative:

- `nature`: sparse-treatment candidates for lighter primary lines and less dominant distribution width.
- `science`: compact-canvas candidates for smaller markers and error caps.
- `acs`: symbol-boundary candidate for non-color-only readability.
- `rsc`: descriptive observations only; no measurable candidate delta yet.
- `elsevier`: broad-canvas marker-size candidate.
- `wiley`: descriptive observations only; no measurable candidate delta yet.
- `cell`: biomedical time-series readability candidate.

No candidate is applied by default. MCP rendering continues to use the existing journal-track tokens. Reports expose candidate deltas and descriptive observations separately so agents can answer why a future opt-in visual difference exists without implying official publisher compliance.
