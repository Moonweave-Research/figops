# HKS 05 — AI-Native FigOps MCP Playbook

FigOps supplies bounded data facts, contained execution, artifact integrity,
provenance, and objective evidence. The agent chooses the plot, authors complex
project-local code, inspects the rendered image, and decides what to revise.
Automatic QA is not publication approval.

## Surface profiles

- `v2` is the launcher default. It exposes at most seven concise tools and
  omits render tools from discovery when writes are disabled.
- `compatibility` exposes the frozen 14 canonical tools and 13 `graphhub.*`
  aliases. Select it with `--surface-profile compatibility` or
  `GRAPH_HUB_MCP_SURFACE_PROFILE=compatibility`.
- Profile selection changes discovery, not security. Containment, provenance,
  statistical-claim checks, and the write guard apply to every handler and
  alias.

Use `figops.describe` without arguments for a small capability index. Add
`kind` and optionally `name` only when detail is needed. Resources do not repeat
full tool schemas.

## Default evidence-first tools

| Tool | Use |
| --- | --- |
| `figops.health` | Inspect readiness, active surface, and write state. |
| `figops.describe` | Fetch a summary, filtered kind list, or one named detail. |
| `figops.list_styles` | Fetch style names only when style support is uncertain. |
| `figops.inspect_data` | Learn bounded columns, types, nulls, ranges, cardinality, and hashes; rows are opt-in. |
| `figops.render_basic_csv` | Render a known-schema scatter, line, or bar figure in one call. |
| `figops.render_project_script` | Execute one declared project-local Python/R figure without code or command strings. |
| `figops.audit_artifact` | Apply explicit policy packs to validated evidence; never returns approval. |

A known-schema CSV normally needs one render call. If columns are unknown, use
one bounded inspection first. A configured project script normally needs one
render call after its source and config exist. The render response already
contains evidence, artifact metadata, manifest URI, and preview URI; neither a
dry run nor a collect call is a prerequisite.

After rendering, inspect the preview image and objective evidence. Revise only
what the evidence or visual review justifies. Preserve raw labels unless an
explicit label map or compatibility transform is requested. Unsupported
statistical annotations must be removed or linked to valid calculation
evidence; they are not stylistic warnings.

## Source mutation

Source-creating or source-restructuring operations remain approval-gated.
`figops.scaffold_project` and `figops.normalize_project_structure` should first
run with `dry_run=true`; show the manifest and apply only after explicit user
approval. This rule does not impose dry-run choreography on isolated render
jobs.

## Compatibility catalog

Compatibility mode retains these canonical handlers:

- `figops.health`, `figops.describe`, `figops.list_styles`,
  `figops.list_projects`, `figops.inspect_project`,
  `figops.validate_project`, `figops.render_csv_graph`,
  `figops.render_csv_multipanel`, `figops.render_project_figure`,
  `figops.collect_artifacts`, `figops.scaffold_project`,
  `figops.normalize_project_structure`, `figops.batch_check`, and
  `figops.evaluate_publication_readiness`.

The four v2 handlers remain callable by their canonical names:
`figops.inspect_data`, `figops.render_basic_csv`,
`figops.render_project_script`, and `figops.audit_artifact`.

The frozen aliases are `graphhub.health`, `graphhub.describe`,
`graphhub.list_styles`, `graphhub.list_projects`, `graphhub.inspect_project`,
`graphhub.validate_project`, `graphhub.render_csv_graph`,
`graphhub.render_csv_multipanel`, `graphhub.render_project_figure`,
`graphhub.collect_artifacts`, `graphhub.scaffold_project`,
`graphhub.normalize_project_structure`, and `graphhub.batch_check`. They cannot
bypass the write guard or strengthened kernel.

Legacy render fields remain available for reproduction. Use explicit
`label_transform="legacy_compress"` only when reproducing old output. New work
uses raw labels and explicit authored mappings.

## Compatibility render example

This example demonstrates the same dataset across public journal styles. These
are independent render calls, not a mandatory sequence. Keep data encodings
fixed and change only style/output controls.

```json
[
  {"tool":"figops.render_csv_graph","arguments":{"data_path":"/allowed/measurements.csv","x_column":"strain","y_column":"stress","series_column":"sample","plot_type":"line","target_format":"nature","output_format":"png","job_id":"journal-nature"}},
  {"tool":"figops.render_csv_graph","arguments":{"data_path":"/allowed/measurements.csv","x_column":"strain","y_column":"stress","series_column":"sample","plot_type":"line","target_format":"science","output_format":"png","job_id":"journal-science"}},
  {"tool":"figops.render_csv_graph","arguments":{"data_path":"/allowed/measurements.csv","x_column":"strain","y_column":"stress","series_column":"sample","plot_type":"line","target_format":"acs","output_format":"png","job_id":"journal-acs"}},
  {"tool":"figops.render_csv_graph","arguments":{"data_path":"/allowed/measurements.csv","x_column":"strain","y_column":"stress","series_column":"sample","plot_type":"line","target_format":"rsc","output_format":"png","job_id":"journal-rsc"}},
  {"tool":"figops.render_csv_graph","arguments":{"data_path":"/allowed/measurements.csv","x_column":"strain","y_column":"stress","series_column":"sample","plot_type":"line","target_format":"elsevier","output_format":"png","job_id":"journal-elsevier"}},
  {"tool":"figops.render_csv_graph","arguments":{"data_path":"/allowed/measurements.csv","x_column":"strain","y_column":"stress","series_column":"sample","plot_type":"line","target_format":"wiley","output_format":"png","job_id":"journal-wiley"}},
  {"tool":"figops.render_csv_graph","arguments":{"data_path":"/allowed/measurements.csv","x_column":"strain","y_column":"stress","series_column":"sample","plot_type":"line","target_format":"cell","output_format":"png","job_id":"journal-cell"}}
]
```

## Evidence interpretation

- Integrity, containment, declared data contracts, missing required provenance,
  corrupt artifacts, and unsupported claims are hard failures.
- Geometry is raw measurement. Severity appears only through an explicitly
  selected policy pack; informational findings do not become hard failures via
  a flat aggregate.
- Hash identity and visual similarity are separate evidence.
- `manual_review_needed=false` is not human or venue approval.
- Preview resources are lazy, manifest-bound, MIME-checked, and size-bounded.

When writes are disabled, `figops.inspect_data`, `figops.audit_artifact`, and
manifest/preview reads remain available. Render, scaffold, normalize, and batch
write handlers are omitted from discovery and fail closed without side effects
if called by a remembered canonical or compatibility name.
