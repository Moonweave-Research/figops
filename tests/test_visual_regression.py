import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub_core.visual_regression import (
    VALID_REGRESSION_BASELINE_MODES,
    _build_baseline_key,
    _normalize_regression_baseline_mode,
    _resolve_project_name,
    _summarize_stdout,
    write_check_all_report,
)


def test_normalize_valid_modes():
    for mode in ("ignore", "check", "update"):
        assert _normalize_regression_baseline_mode(mode) == mode


def test_normalize_strips_whitespace():
    assert _normalize_regression_baseline_mode("  ignore  ") == "ignore"


def test_normalize_invalid_mode_raises():
    try:
        _normalize_regression_baseline_mode("invalid_mode")
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "invalid" in str(exc).lower()
        assert "ignore" in str(exc)


def test_normalize_none_defaults_to_ignore():
    assert _normalize_regression_baseline_mode(None) == "ignore"


def test_valid_modes_set():
    assert VALID_REGRESSION_BASELINE_MODES == {"ignore", "check", "update"}


def test_build_baseline_key_is_deterministic(tmp_path):
    key1 = _build_baseline_key(str(tmp_path), "Fig1")
    key2 = _build_baseline_key(str(tmp_path), "Fig1")
    assert key1 == key2
    assert len(key1) == 64  # sha256 hex digest


def test_build_baseline_key_differs_by_figure_id(tmp_path):
    key1 = _build_baseline_key(str(tmp_path), "Fig1")
    key2 = _build_baseline_key(str(tmp_path), "Fig2")
    assert key1 != key2


def test_build_baseline_key_differs_by_project_dir(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    key1 = _build_baseline_key(str(tmp_path), "Fig1")
    key2 = _build_baseline_key(str(other), "Fig1")
    assert key1 != key2


def test_resolve_project_name_from_config(tmp_path):
    config = {"project": {"name": "My Research Project"}}
    assert _resolve_project_name(str(tmp_path), config) == "My Research Project"


def test_resolve_project_name_fallback_to_dirname(tmp_path):
    project_dir = tmp_path / "03_MyProject"
    project_dir.mkdir()
    assert _resolve_project_name(str(project_dir), {}) == "03_MyProject"


def test_resolve_project_name_empty_name_fallback(tmp_path):
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir()
    config = {"project": {"name": "   "}}
    assert _resolve_project_name(str(project_dir), config) == "TestProject"


def test_summarize_stdout_short_output():
    lines = ["line 1", "line 2", "line 3"]
    result = _summarize_stdout("\n".join(lines))
    assert result == lines


def test_summarize_stdout_truncates_long_output():
    lines = [f"line {i}" for i in range(50)]
    result = _summarize_stdout("\n".join(lines))
    assert len(result) == 20
    assert result[-1] == "line 49"


def test_summarize_stdout_strips_blank_lines():
    result = _summarize_stdout("a\n\n\nb\n\n")
    assert result == ["a", "b"]


def test_write_check_all_report_creates_file(tmp_path):
    report = {
        "schema_version": 3,
        "success": True,
        "results": [],
        "project_count": 0,
    }

    with patch("hub_core.visual_regression.resolve_runtime_root", return_value=str(tmp_path)):
        report_path = write_check_all_report(str(tmp_path), report, log_dirname=str(tmp_path))

    assert Path(report_path).exists()
    loaded = json.loads(Path(report_path).read_text())
    assert loaded["success"] is True


def test_write_check_all_report_rejects_non_dict(tmp_path):
    try:
        write_check_all_report(str(tmp_path), "not a dict")
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "dict" in str(exc).lower()
