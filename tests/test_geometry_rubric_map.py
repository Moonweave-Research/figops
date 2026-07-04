from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hub_core.mcp.render_geometry_schemas import GEOMETRY_METRIC_NAMES
from scripts.check_geometry_rubric_map import (
    CheckPassed,
    RubricMapPaths,
    classify_diagnostic,
    validate_rubric_map,
)

HUB_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = HUB_ROOT / "docs" / "specs" / "geometry-diagnostic-rubric-map.json"
QA_PATH = HUB_ROOT / "docs" / "QA.md"
RUBRIC_PATH = HUB_ROOT / "docs" / "specs" / "2026-06-30-figure-quality-rubric.md"


def test_geometry_rubric_map_covers_canonical_metrics() -> None:
    # Given: the committed diagnostic-to-rubric mapping.
    paths = RubricMapPaths(mapping=MAP_PATH, qa_doc=QA_PATH, rubric_doc=RUBRIC_PATH)

    # When: the checker validates it against the live geometry schema.
    result = validate_rubric_map(paths)

    # Then: every canonical metric is mapped exactly once.
    assert result.errors == []
    assert result.metric_count == len(GEOMETRY_METRIC_NAMES)


def test_checker_rejects_missing_canonical_metric(tmp_path: Path) -> None:
    # Given: a mapping with one live geometry metric removed.
    data = _load_mapping()
    metrics = dict(data["metrics"])
    metrics.pop(GEOMETRY_METRIC_NAMES[0])
    data["metrics"] = metrics
    mapping_path = _write_mapping(tmp_path, data)

    # When: the checker validates the incomplete mapping.
    result = validate_rubric_map(_paths_for(mapping_path))

    # Then: it reports the missing metric by name.
    assert any(GEOMETRY_METRIC_NAMES[0] in error for error in result.errors)


def test_checker_rejects_invalid_rubric_id(tmp_path: Path) -> None:
    # Given: a mapping entry with a non-rubric identifier.
    data = _load_mapping()
    first_metric = GEOMETRY_METRIC_NAMES[0]
    data["metrics"][first_metric]["rubric_id"] = "FQ-X9"
    mapping_path = _write_mapping(tmp_path, data)

    # When: the checker validates the mapping.
    result = validate_rubric_map(_paths_for(mapping_path))

    # Then: the invalid rubric ID is rejected.
    assert any("FQ-X9" in error for error in result.errors)


def test_hard_gate_passed_none_is_unmeasured_not_pass() -> None:
    # Given: a hard-gate diagnostic whose measurement was skipped.
    entry = _load_mapping()["metrics"]["tick_label_overlaps"]

    # When: the checker classifies the tri-state diagnostic result.
    classification = classify_diagnostic(entry, CheckPassed.UNMEASURED)

    # Then: unmeasured hard gates block review rather than passing.
    assert classification.status == "blocked"
    assert classification.counts_as_pass is False


def test_checker_rejects_stale_docs_without_map_pointer(tmp_path: Path) -> None:
    # Given: documentation that no longer points to the machine-readable source.
    stale_qa = tmp_path / "QA.md"
    stale_rubric = tmp_path / "rubric.md"
    stale_qa.write_text("Diagnostic name mapping for current render outputs.", encoding="utf-8")
    stale_rubric.write_text("Existing Diagnostic Name Map", encoding="utf-8")

    # When: the checker validates docs freshness.
    result = validate_rubric_map(RubricMapPaths(mapping=MAP_PATH, qa_doc=stale_qa, rubric_doc=stale_rubric))

    # Then: missing source-of-truth pointers fail the check.
    assert any("geometry-diagnostic-rubric-map.json" in error for error in result.errors)


def test_checker_rejects_stale_docs_missing_metric_name(tmp_path: Path) -> None:
    # Given: docs that point to the map but omit one canonical metric name.
    stale_qa = tmp_path / "QA.md"
    stale_rubric = tmp_path / "rubric.md"
    metric_text = "\n".join(GEOMETRY_METRIC_NAMES[1:])
    docs_text = (
        "docs/specs/geometry-diagnostic-rubric-map.json\n"
        "scripts/check_geometry_rubric_map.py\n"
        f"{metric_text}\n"
    )
    stale_qa.write_text(docs_text, encoding="utf-8")
    stale_rubric.write_text(docs_text, encoding="utf-8")

    # When: the checker validates the stale docs.
    result = validate_rubric_map(RubricMapPaths(mapping=MAP_PATH, qa_doc=stale_qa, rubric_doc=stale_rubric))

    # Then: the missing metric keeps docs from silently drifting.
    assert any(GEOMETRY_METRIC_NAMES[0] in error for error in result.errors)


def test_cli_success_output_reports_exact_metric_count() -> None:
    # Given: the committed checker CLI.
    command = [sys.executable, "scripts/check_geometry_rubric_map.py"]

    # When: it is run from the repository root.
    completed = subprocess.run(command, cwd=HUB_ROOT, check=True, capture_output=True, text=True)

    # Then: success output names the exact checked contract instead of a generic OK.
    assert f"{len(GEOMETRY_METRIC_NAMES)} geometry_diagnostics/1 metrics mapped exactly once" in completed.stdout


def _load_mapping():
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _write_mapping(tmp_path: Path, data) -> Path:
    mapping_path = tmp_path / "geometry-diagnostic-rubric-map.json"
    mapping_path.write_text(json.dumps(data), encoding="utf-8")
    return mapping_path


def _paths_for(mapping_path: Path) -> RubricMapPaths:
    return RubricMapPaths(mapping=mapping_path, qa_doc=QA_PATH, rubric_doc=RUBRIC_PATH)
