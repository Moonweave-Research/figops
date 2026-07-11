import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from hub_core.visual_regression import (
    VALID_REGRESSION_BASELINE_MODES,
    _build_baseline_key,
    _build_output_record,
    _evaluate_pixel_verdict,
    _load_baseline_state,
    _normalize_regression_baseline_mode,
    _resolve_figure_baseline,
    _resolve_project_name,
    _resolve_regression_tolerances,
    _summarize_stdout,
    _upsert_baseline_entry,
    _write_baseline_manifest,
    write_check_all_report,
)

PIL_Image = None
try:
    from PIL import Image as PIL_Image
except Exception:
    PIL_Image = None


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


def test_baseline_state_facade_preserves_runtime_root_and_snapshot_contract(tmp_path):
    output_path = tmp_path / "Fig1.png"
    output_path.write_bytes(b"fixture-output")
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with patch("hub_core.visual_regression.resolve_hub_logs_dir", return_value=str(tmp_path / "logs")):
        state = _load_baseline_state("ignored")

    key = _build_baseline_key(str(project_dir), "Fig1")
    entry = _upsert_baseline_entry(
        state,
        key=key,
        project_dir=str(project_dir),
        project_name="project",
        figure_id="Fig1",
        output_path=str(output_path),
        current_hash=_sha256(output_path),
        current_size=output_path.stat().st_size,
    )
    _write_baseline_manifest(state)

    assert Path(entry["baseline_path"]).read_bytes() == output_path.read_bytes()
    assert state["was_updated"] is True
    stored = json.loads(Path(state["manifest_path"]).read_text(encoding="utf-8"))
    assert stored["figures"][key]["baseline_relpath"].startswith("files/")


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


# --- Check-mode pixel gating ------------------------------------------------

requires_pil = pytest.mark.skipif(PIL_Image is None, reason="Pillow not available")


def _write_solid_png(path, size, color):
    PIL_Image.new("RGB", size, color).save(path)
    return str(path)


def _make_check_state(tmp_path, baseline_path, baseline_hash):
    """Build a baseline_state whose single figure entry points at baseline_path.

    Contract: baseline_path is the immutable reference image. The manifest stores
    its literal path and the hash captured here, so callers must NOT overwrite the
    file at baseline_path after this returns (write the current/jittered image to a
    distinct path instead), or the recorded hash will no longer match its bytes.
    """
    project_dir = str(tmp_path / "proj")
    Path(project_dir).mkdir(exist_ok=True)
    key = _build_baseline_key(project_dir, "Fig1")
    manifest = {
        "schema_version": 1,
        "updated_at": None,
        "figures": {
            key: {
                "baseline_path": baseline_path,
                "sha256": baseline_hash,
                "figure_id": "Fig1",
            }
        },
    }
    state = {
        "baseline_dir": str(tmp_path / "bl"),
        "files_dir": str(tmp_path / "bl" / "files"),
        "manifest_path": str(tmp_path / "bl" / "manifest.json"),
        "manifest": manifest,
        "dirty": False,
        "was_updated": False,
    }
    return state, project_dir


def _sha256(path):
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolve(state, project_dir, output_path, tolerances=None):
    return _resolve_figure_baseline(
        state,
        project_dir=project_dir,
        project_name="proj",
        figure_id="Fig1",
        output_path=output_path,
        regression_baseline="check",
        tolerances=tolerances or _resolve_regression_tolerances(None),
    )


@requires_pil
def test_check_identical_bytes_pass(tmp_path):
    baseline = _write_solid_png(tmp_path / "base.png", (32, 32), (10, 20, 30))
    current = _write_solid_png(tmp_path / "cur.png", (32, 32), (10, 20, 30))
    state, project_dir = _make_check_state(tmp_path, baseline, _sha256(baseline))

    result = _resolve(state, project_dir, current)
    assert result["regression_ok"] is True
    assert result["status"] == "matched"


@requires_pil
def test_check_jitter_within_tol_pass(tmp_path):
    # Same dimensions, a few pixels differ → small ratio/rms. Loosen tolerances.
    baseline = _write_solid_png(tmp_path / "base.png", (100, 100), (128, 128, 128))
    img = PIL_Image.new("RGB", (100, 100), (128, 128, 128))
    # perturb a handful of pixels slightly
    for x in range(5):
        img.putpixel((x, 0), (130, 128, 128))
    current = str(tmp_path / "cur.png")
    img.save(current)
    state, project_dir = _make_check_state(tmp_path, baseline, _sha256(baseline))

    assert _sha256(baseline) != _sha256(current)  # hashes truly differ
    tol = {"pixel_diff_ratio_tol": 0.01, "pixel_rms_tol": 5.0}
    result = _resolve(state, project_dir, current, tolerances=tol)
    assert result["regression_ok"] is True
    assert result["status"] == "within_tolerance"


@requires_pil
def test_check_single_pixel_below_rounding_threshold_fails(tmp_path):
    # Witnesses the rounding-gate fix: 1 changed pixel in a 1600x1600 image
    # gives pixel_diff_ratio_raw ~= 3.9e-7, which rounds to 0.000000 at 6 dp.
    # With strict 0.0 tolerances the verdict must use the raw metric and fail,
    # not the rounded 0.000000 that would pass-open.
    baseline = _write_solid_png(tmp_path / "base.png", (1600, 1600), (128, 128, 128))
    img = PIL_Image.new("RGB", (1600, 1600), (128, 128, 128))
    img.putpixel((0, 0), (129, 128, 128))
    current = str(tmp_path / "cur.png")
    img.save(current)
    state, project_dir = _make_check_state(tmp_path, baseline, _sha256(baseline))

    assert _sha256(baseline) != _sha256(current)
    result = _resolve(state, project_dir, current)  # default tol 0.0/0.0
    assert result["regression_ok"] is False
    assert result["status"] == "mismatch"


@requires_pil
def test_check_beyond_tol_fail(tmp_path):
    baseline = _write_solid_png(tmp_path / "base.png", (100, 100), (0, 0, 0))
    current = _write_solid_png(tmp_path / "cur.png", (100, 100), (255, 255, 255))
    state, project_dir = _make_check_state(tmp_path, baseline, _sha256(baseline))

    # generous-but-finite tolerances still cannot accept a fully inverted image
    tol = {"pixel_diff_ratio_tol": 0.5, "pixel_rms_tol": 50.0}
    result = _resolve(state, project_dir, current, tolerances=tol)
    assert result["regression_ok"] is False
    assert result["status"] == "mismatch"
    assert "tolerance" in result.get("reason", "")


@requires_pil
def test_check_default_tolerances_fail_on_any_pixel_diff(tmp_path):
    baseline = _write_solid_png(tmp_path / "base.png", (50, 50), (100, 100, 100))
    img = PIL_Image.new("RGB", (50, 50), (100, 100, 100))
    img.putpixel((0, 0), (101, 100, 100))
    current = str(tmp_path / "cur.png")
    img.save(current)
    state, project_dir = _make_check_state(tmp_path, baseline, _sha256(baseline))

    result = _resolve(state, project_dir, current)  # default tol 0.0/0.0
    assert result["regression_ok"] is False
    assert result["status"] == "mismatch"


@requires_pil
def test_check_size_mismatch_fails_outright(tmp_path):
    baseline = _write_solid_png(tmp_path / "base.png", (40, 40), (50, 50, 50))
    current = _write_solid_png(tmp_path / "cur.png", (80, 40), (50, 50, 50))
    state, project_dir = _make_check_state(tmp_path, baseline, _sha256(baseline))

    # even with wide-open tolerances, a size mismatch must fail
    tol = {"pixel_diff_ratio_tol": 1.0, "pixel_rms_tol": 255.0}
    result = _resolve(state, project_dir, current, tolerances=tol)
    assert result["regression_ok"] is False
    assert result["status"] == "size_mismatch"
    assert "dimensions differ" in result.get("reason", "")


def test_evaluate_pixel_verdict_missing_metrics_fail_closed():
    ok, status, reason = _evaluate_pixel_verdict(None, _resolve_regression_tolerances(None))
    assert ok is False
    assert status == "mismatch"
    assert reason


def test_resolve_tolerances_defaults_strict():
    tol = _resolve_regression_tolerances(None)
    assert tol == {"pixel_diff_ratio_tol": 0.0, "pixel_rms_tol": 0.0}


def test_resolve_tolerances_reads_config():
    config = {"regression": {"pixel_diff_ratio_tol": 0.02, "pixel_rms_tol": 3.5}}
    tol = _resolve_regression_tolerances(config)
    assert tol == {"pixel_diff_ratio_tol": 0.02, "pixel_rms_tol": 3.5}


def test_resolve_tolerances_rejects_bad_values():
    config = {"regression": {"pixel_diff_ratio_tol": -1, "pixel_rms_tol": "x"}}
    tol = _resolve_regression_tolerances(config)
    assert tol == {"pixel_diff_ratio_tol": 0.0, "pixel_rms_tol": 0.0}


def test_build_output_record_missing_regression_ok_defaults_false(tmp_path):
    # A baseline_result dict missing "regression_ok" must fail closed: the old
    # .get(..., True) default would have silently passed it.
    output_path = str(tmp_path / "fig.png")
    with patch(
        "hub_core.visual_regression._resolve_figure_baseline",
        return_value={},
    ):
        record = _build_output_record(
            None,
            project_dir=str(tmp_path),
            project_name="proj",
            figure_id="Fig1",
            output_path=output_path,
            regression_baseline="check",
            tolerances=_resolve_regression_tolerances(None),
            artifact_kind="declared",
        )
    assert record["regression_ok"] is False
