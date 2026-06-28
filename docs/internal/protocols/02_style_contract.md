# HKS 02 Style Contract

FigOps owns the central style system.

## Target Formats

Allowed target formats:

```text
acs
cell
default
elsevier
nature
internal_style_format
ppt
rsc
science
wiley
```

`internal_style_format` is first-class and must not be treated as an alias or temporary experiment.

## Profiles

Current profiles:

```text
baseline
internal_style_profile
```

Profile aliases are defined in `themes/style_profiles.py`.

## Output Formats

Allowed output formats:

```text
png
pdf
svg
```

## Style Resolution Order

Style resolution order is:

```text
visual_style < preset < per-step inline override
```

## Agent Rules

- Call `figops.list_styles` before assuming style support.
- Do not copy Athena's style enum into FigOps.
- Do not invent styles in project configs.
- If a requested style is missing, return the supported style list and ask whether to map to an existing style or add a new central style.
