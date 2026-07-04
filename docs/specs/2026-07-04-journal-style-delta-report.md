# Journal Style Delta Report Contract

Date: 2026-07-04

Schema: `docs/specs/2026-07-04-journal-style-delta-report.schema.json`

## Purpose

The style-delta report is a machine-readable comparison artifact for journal-track renders produced through `figops.render_csv_graph`. It explains how one public journal track differs from a reference track for the same fixture dataset, output format, and renderer surface.

The report is publication-oriented evidence only. It is not a publishable verdict, not an acceptance prediction, and not proof that a figure satisfies the latest external publisher requirements. It supports review by making token, render, diagnostic, and visual-language differences explicit.

## Baseline Gap

Current journal fixture summaries expose `style_summary`, selected token floors, `geometry_diagnostics`, `layout_report`, and `manual_review_needed`. That proves important runtime fields are present, but it does not explain how tracks differ from one another or why a difference is appropriate.

The requested dogfood summary path, `.omo/dogfood/journal-track-mcp-20260704-file/summary.json`, was not present in this worktree during this task. The local fixture test still shows the current contract shape and the missing comparison layer.

## Required Groups

Every style-delta report has top-level run metadata, comparison scope, a reference track, comparison tracks, a list of per-track deltas, and a claim boundary.

Each per-track delta must include these groups:

- `token_delta`: Compares encoded style inputs such as dimensions, font floors, line floors, marker grammar, palette tokens, and legend tokens.
- `render_delta`: Compares rendered-output facts such as output dimensions, layout density, legend behavior, artifact paths, and descriptive output metrics.
- `diagnostic_delta`: Compares status, manual-review state, geometry diagnostics, layout report results, failed checks, passed checks, and unmeasured states.
- `visual_language_rationale`: States why the difference exists and how strongly it is supported.

`visual_language_rationale` is required because visual differences without rationale are easy to make artificial. Acceptable rationale categories are official submission constraints, encoded FigOps tokens, observed visual language, heuristic publication conventions, and explicitly unsupported or deferred items. The machine-readable category values are `official_submission_constraint`, `encoded_figops_token`, `observed_visual_language`, `heuristic_publication_convention`, and `unsupported_or_deferred`.

## Quality Boundary

The report must not require arbitrary pixel-difference thresholds as proof of quality. Pixel dimensions, file size, and other rendered-output metrics can be recorded as facts, but quality remains tied to explicit diagnostics, fixture expectations, manual-review state, source-backed rationale, and human review where required.

Style-delta evidence is comparison evidence, not a publishable verdict. `manual_review_needed=false` and a clean layout report are useful signals, but they do not independently make a figure publishable. Product and documentation wording should stay at publication-oriented unless a separate hard-gate review supports a narrower claim.

## Minimal Shape

```json
{
  "schema_version": "journal_style_delta_report/1",
  "report_kind": "style-delta",
  "generated_at": "2026-07-04T00:00:00Z",
  "comparison_scope": {
    "fixture_id": "basic_series",
    "input_dataset": "tests/fixtures/journal_tracks/basic_series.csv",
    "renderer_surface": "figops.render_csv_graph",
    "output_format": "png",
    "tracks": ["nature", "science"]
  },
  "baseline_track": "nature",
  "comparison_tracks": ["science"],
  "track_deltas": [
    {
      "track": "science",
      "reference_track": "nature",
      "token_delta": {
        "dimension_tokens": {},
        "font_floor_tokens": {},
        "line_floor_tokens": {},
        "marker_grammar_tokens": {},
        "palette_tokens": {},
        "legend_tokens": {}
      },
      "render_delta": {
        "output_dimensions": {},
        "layout_density": {},
        "legend_behavior": {},
        "rendered_output_metrics": {
          "width_px": 1200,
          "height_px": 800,
          "file_size_bytes": 1000,
          "pixel_threshold_policy": "not_used_as_quality_proof"
        },
        "artifact_paths": []
      },
      "diagnostic_delta": {
        "status_delta": {
          "reference": "ok",
          "candidate": "ok",
          "delta": "unchanged",
          "interpretation": "Both renders completed without warning."
        },
        "manual_review_delta": {
          "reference": false,
          "candidate": false,
          "delta": false,
          "interpretation": "No additional manual-review signal was introduced."
        },
        "geometry_diagnostics": {
          "passed_count_delta": 0,
          "failed_count_delta": 0,
          "unmeasured_count_delta": 0,
          "notable_checks": []
        },
        "layout_report": {
          "passed_count_delta": 0,
          "failed_count_delta": 0,
          "unmeasured_count_delta": 0,
          "notable_checks": []
        }
      },
      "visual_language_rationale": {
        "summary": "Science uses a compact-width track relative to the reference.",
        "rationale_category": "encoded_figops_token",
        "evidence_basis": ["themes/style_profiles.py baseline tokens"],
        "unsupported_or_deferred": [],
        "claim_boundary": "publication-oriented comparison evidence, not a publishable verdict"
      }
    }
  ],
  "claim_boundary": {
    "evidence_role": "comparison_evidence_only",
    "publishable_verdict": "not_a_publishable_verdict",
    "quality_threshold_policy": "no_arbitrary_pixel_difference_thresholds",
    "review_requirement": "Use this report to support review; do not treat it as publisher acceptance."
  }
}
```
