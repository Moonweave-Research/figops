"""Tests for glob input expansion."""
import sys
from pathlib import Path

import pytest  # noqa: F401  — tmp_path and capsys fixtures are injected by name

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub_core.config_parser import validate_config
from hub_core.utils import expand_glob_inputs, flatten_glob_results


# ---------------------------------------------------------------------------
# Minimal valid config base — reused for validate_config tests
# ---------------------------------------------------------------------------
def _base_config(**overrides) -> dict:
    cfg = {
        "project": {"name": "Test Project"},
        "visual_style": {"target_format": "nature", "font_scale": 1.0, "profile": "baseline"},
        "language_policy": {"analysis_lang": "r", "plot_lang": "python"},
    }
    cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# expand_glob_inputs
# ---------------------------------------------------------------------------

def test_expand_glob_no_magic(tmp_path):
    plain = "data/results.csv"
    result = expand_glob_inputs(str(tmp_path), [plain])
    assert len(result) == 1
    pattern, paths = result[0]
    assert pattern == plain
    assert paths == [str(tmp_path / plain)]


def test_expand_glob_matches_files(tmp_path):
    (tmp_path / "a.csv").write_text("x,y\n1,2\n")
    (tmp_path / "b.csv").write_text("x,y\n3,4\n")
    (tmp_path / "notes.txt").write_text("ignore me\n")

    result = expand_glob_inputs(str(tmp_path), ["*.csv"])
    assert len(result) == 1
    pattern, paths = result[0]
    assert pattern == "*.csv"
    basenames = sorted(Path(p).name for p in paths)
    assert basenames == ["a.csv", "b.csv"]
    # Results must be sorted
    assert paths == sorted(paths)


def test_expand_glob_zero_matches(tmp_path, capsys):
    result = expand_glob_inputs(str(tmp_path), ["*.csv"])
    pattern, paths = result[0]
    assert paths == []
    captured = capsys.readouterr()
    assert "WARN" in captured.out or "warn" in captured.out.lower()


def test_expand_glob_ignores_directories(tmp_path):
    (tmp_path / "subdir.csv").mkdir()   # directory with .csv extension
    (tmp_path / "real.csv").write_text("a,b\n1,2\n")

    result = expand_glob_inputs(str(tmp_path), ["*.csv"])
    _, paths = result[0]
    # Only the actual file should be returned, not the directory
    assert all(Path(p).is_file() for p in paths)
    assert len(paths) == 1
    assert Path(paths[0]).name == "real.csv"


def test_expand_glob_recursive(tmp_path):
    sub = tmp_path / "nested"
    sub.mkdir()
    (tmp_path / "top.csv").write_text("x\n1\n")
    (sub / "deep.csv").write_text("x\n2\n")

    result = expand_glob_inputs(str(tmp_path), ["**/*.csv"])
    _, paths = result[0]
    basenames = sorted(Path(p).name for p in paths)
    assert "top.csv" in basenames
    assert "deep.csv" in basenames


# ---------------------------------------------------------------------------
# flatten_glob_results
# ---------------------------------------------------------------------------

def test_flatten_glob_results():
    glob_results = [
        ("*.csv", ["/proj/a.csv", "/proj/b.csv"]),
        ("fig.png", ["/proj/fig.png"]),
    ]
    flat = flatten_glob_results(glob_results)
    assert flat == ["/proj/a.csv", "/proj/b.csv", "/proj/fig.png"]


# ---------------------------------------------------------------------------
# validate_config — expand field validation
# ---------------------------------------------------------------------------

def test_expand_validates_in_config():
    config = _base_config(
        pipeline={
            "analysis": [{
                "script": "run.r",
                "expand": "invalid_mode",
            }]
        }
    )
    errors = validate_config(config)
    assert any("expand" in e and "batch" in e for e in errors)


def test_expand_each_requires_stem():
    config = _base_config(
        figures=[{
            "script": "plot.py",
            "output": "Fig_no_stem.png",   # missing {stem}
            "expand": "each",
        }]
    )
    errors = validate_config(config)
    assert any("{stem}" in e for e in errors)
