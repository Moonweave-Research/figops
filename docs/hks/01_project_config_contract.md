# HKS 01 Project Config Contract

`project_config.yaml` is the graph project API.

## Required Sections

- `project`
- `visual_style`
- `language_policy`
- `data_contract`
- `pipeline`
- `figures`

## Standard Project Layout

```text
project/
  README.md
  task.md
  project_config.yaml
  raw/
  work/
  hub_scripts/
  results/data/
  results/figures/
  results/final/
  docs/
  archive/
```

## Style Selection

Projects select styles; they do not redefine central FigOps styles.

```yaml
visual_style:
  target_format: nature_surfur
  font_scale: 1.0
  profile: baseline
```

Use `presets` for repeated bundles:

```yaml
presets:
  journal_svg:
    target_format: nature
    font_scale: 1.0
    profile: baseline
    output_format: svg
  _default: journal_svg
```

## Validation Rules

- `visual_style.target_format` must be one of FigOps's canonical target formats.
- `visual_style.profile` must be a known FigOps profile or alias.
- `data_contract.csv_checks[].path` is required.
- `data_contract.csv_checks[].semantic_checks.<column>.monotonic` may be one of
  `increasing`, `decreasing`, `nondecreasing`, or `nonincreasing`.
- `figures[].script`, `figures[].inputs`, and `figures[].output` must be concrete paths.
- Legacy `scripts/project_config.yaml` can be inspected, but new projects use root `project_config.yaml`.

## Migration Rule

Project normalization must run dry-run first. Apply mode must return a manifest of created, modified, and skipped paths.
