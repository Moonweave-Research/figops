# Figure Quality Rubric Receipt - 2026-06-30.D

Plan: `docs/specs/2026-06-30-figure-quality-rubric.plan.json`

## Confirmed

| Claim | Evidence |
| --- | --- |
| Rubric markdown exists. | `docs/specs/2026-06-30-figure-quality-rubric.md` defines objective, scope, non-goals, hard gates, advisory polish, diagnostic mapping policy, acceptance criteria, and verification commands. |
| Machine-readable plan exists and parses as JSON. | `python3 -m json.tool docs/specs/2026-06-30-figure-quality-rubric.plan.json >/dev/null` returned exit 0. |
| Rubric IDs are present in markdown. | Python markdown sanity check found `FQ-H1` through `FQ-H5` and `FQ-A1` through `FQ-A5`, plus required section headings. |
| Plan IDs match markdown IDs. | Python plan/markdown consistency check returned exit 0. |
| QA guide links the rubric. | Python QA sanity check found `2026-06-30-figure-quality-rubric.md` in `docs/QA.md`. |
| Existing diagnostic names are mapped to rubric IDs. | Rubric and QA now map `validate_figure_preflight` checks plus current `geometry_diagnostics/1` names, including `legend_data_collision` as informational and `label_offset_consistency` as advisory. |
| Markdown tables are mechanically sane. | Python markdown sanity check found no tab characters and no unterminated pipe-table rows in the touched docs. |

## Refuted

| Claim | Refutation |
| --- | --- |
| Code changes were needed for this slice. | The requested rubric is documentation-only; verification used JSON and markdown sanity checks only. |

## Unverified

| Item | Reason |
| --- | --- |
| Runtime rendering behavior. | Out of scope for this Lane D documentation slice. |
| Full pytest suite. | Out of scope because no code changed; the slice is testable through deterministic docs sanity checks. |
| Human visual review quality on real figures. | The rubric defines the review contract but does not apply it to rendered project artifacts in this slice. |

## Final Commands

```bash
python3 -m json.tool docs/specs/2026-06-30-figure-quality-rubric.plan.json >/dev/null
python3 - <<'PY'
from pathlib import Path
md = Path("docs/specs/2026-06-30-figure-quality-rubric.md").read_text(encoding="utf-8")
required = ["FQ-H1", "FQ-H2", "FQ-H3", "FQ-H4", "FQ-H5", "FQ-A1", "FQ-A2", "FQ-A3", "FQ-A4", "FQ-A5"]
missing = [item for item in required if item not in md]
if missing:
    raise SystemExit(f"missing rubric ids: {missing}")
for phrase in ["Hard Gates", "Advisory Polish", "Diagnostic Mapping Policy"]:
    if phrase not in md:
        raise SystemExit(f"missing section: {phrase}")
for name in ["legend_data_collision", "label_offset_consistency", "geometry_diagnostics/1"]:
    if name not in md:
        raise SystemExit(f"missing diagnostic mapping: {name}")
PY
python3 - <<'PY'
from pathlib import Path
qa = Path("docs/QA.md").read_text(encoding="utf-8")
if "2026-06-30-figure-quality-rubric.md" not in qa:
    raise SystemExit("QA guide does not link the figure quality rubric")
for name in ["legend_data_collision", "label_offset_consistency", "validate_figure_preflight", "geometry_diagnostics/1"]:
    if name not in qa:
        raise SystemExit(f"QA guide missing diagnostic mapping: {name}")
PY
python3 - <<'PY'
import json
from pathlib import Path
plan = json.loads(Path("docs/specs/2026-06-30-figure-quality-rubric.plan.json").read_text(encoding="utf-8"))
md = Path("docs/specs/2026-06-30-figure-quality-rubric.md").read_text(encoding="utf-8")
ids = [item["id"] for item in plan["hard_gates"]] + [item["id"] for item in plan["advisory_polish"]]
missing = [item for item in ids if item not in md]
if missing:
    raise SystemExit(f"plan ids missing from markdown: {missing}")
expected = {"FQ-H1", "FQ-H2", "FQ-H3", "FQ-H4", "FQ-H5", "FQ-A1", "FQ-A2", "FQ-A3", "FQ-A4", "FQ-A5"}
if set(ids) != expected:
    raise SystemExit(f"unexpected plan ids: {ids}")
for entry in plan.get("diagnostic_mapping", []):
    if entry["rubric"] != "informational" and not any(token in entry["rubric"] for token in expected):
        raise SystemExit(f"bad mapping rubric: {entry}")
    for name in entry["names"]:
        if name not in md:
            raise SystemExit(f"mapping name missing from markdown: {name}")
PY
python3 - <<'PY'
from pathlib import Path
for path in [Path("docs/QA.md"), Path("docs/specs/2026-06-30-figure-quality-rubric.md"), Path("docs/specs/2026-06-30-figure-quality-rubric.receipt.md")]:
    text = path.read_text(encoding="utf-8")
    if "\t" in text:
        raise SystemExit(f"{path}: tab character found")
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("|") and not line.endswith("|"):
            raise SystemExit(f"{path}:{lineno}: markdown table row does not end with |")
print("markdown sanity ok")
PY
```

All final commands returned exit 0.

## Residual Risk

- The rubric is a review contract, not automated enforcement.
- Some existing diagnostics can legitimately skip based on output format,
  renderer availability, or render budget; reviewers must record acceptable skip
  reasons.
- Advisory polish still requires human judgment until future deterministic
  diagnostics are designed and mapped to rubric IDs.
- `legend_data_collision` remains informational because the current diagnostic is
  a bbox-union approximation and is not an ink-accurate collision gate.
