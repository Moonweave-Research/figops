"""Tests for config preset resolution and validation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub_core.config_parser import resolve_presets, resolve_step_style, validate_config
from themes.journal_theme import STYLE_PRESETS


# ---------------------------------------------------------------------------
# Minimal valid config base — reused across tests that need validate_config
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
# resolve_presets
# ---------------------------------------------------------------------------

def test_resolve_presets_empty():
    config = _base_config()
    result = resolve_presets(config)
    assert result == {"__default_name__": None}


def test_resolve_presets_with_default():
    config = _base_config(presets={
        "_default": "journal",
        "journal": {"target_format": "nature", "font_scale": 1.2},
    })
    result = resolve_presets(config)
    assert result["__default_name__"] == "journal"
    assert "journal" in result
    assert result["journal"]["target_format"] == "nature"
    assert result["journal"]["font_scale"] == 1.2


def test_resolve_presets_merges_visual_style():
    config = _base_config(
        visual_style={"target_format": "nature", "font_scale": 1.0, "profile": "baseline"},
        presets={
            "ppt_style": {"target_format": "ppt", "font_scale": 1.5},
        },
    )
    result = resolve_presets(config)
    # target_format overridden by preset
    assert result["ppt_style"]["target_format"] == "ppt"
    assert result["ppt_style"]["font_scale"] == 1.5
    # profile from visual_style base survives
    assert result["ppt_style"]["profile"] == "baseline"


# ---------------------------------------------------------------------------
# resolve_step_style
# ---------------------------------------------------------------------------

def test_resolve_step_style_no_preset():
    config = _base_config(
        visual_style={"target_format": "science", "font_scale": 0.9, "profile": "baseline"},
    )
    step = {"script": "plot.py", "output": "Fig1.png"}
    result = resolve_step_style(step, config, resolved_presets=None)
    assert result["target_format"] == "science"
    assert result["font_scale"] == 0.9
    assert result["profile"] == "baseline"


def test_resolve_step_style_with_preset():
    config = _base_config(
        visual_style={"target_format": "nature", "font_scale": 1.0, "profile": "baseline"},
        presets={"journal": {"target_format": "science", "font_scale": 1.3}},
    )
    resolved = resolve_presets(config)
    step = {"script": "plot.py", "output": "Fig1.png", "preset": "journal"}
    result = resolve_step_style(step, config, resolved_presets=resolved)
    assert result["target_format"] == "science"
    assert result["font_scale"] == 1.3


def test_resolve_step_style_inline_override():
    config = _base_config(
        presets={"journal": {"target_format": "nature", "font_scale": 1.2}},
    )
    resolved = resolve_presets(config)
    step = {
        "script": "plot.py",
        "output": "Fig1.png",
        "preset": "journal",
        "font_scale": 2.0,
        "target_format": "ppt",
    }
    result = resolve_step_style(step, config, resolved_presets=resolved)
    # Inline values must win over preset
    assert result["target_format"] == "ppt"
    assert result["font_scale"] == 2.0


def test_resolve_step_style_default_preset():
    config = _base_config(
        visual_style={"target_format": "nature", "font_scale": 1.0, "profile": "baseline"},
        presets={
            "_default": "journal",
            "journal": {"target_format": "science", "font_scale": 1.1},
        },
    )
    resolved = resolve_presets(config)
    step = {"script": "plot.py", "output": "Fig1.png"}  # no explicit preset key
    result = resolve_step_style(step, config, resolved_presets=resolved)
    # Should pick up _default preset "journal"
    assert result["target_format"] == "science"
    assert result["font_scale"] == 1.1


def test_resolve_step_style_legacy_theme():
    config = _base_config(
        visual_style={"target_format": "nature", "font_scale": 1.0, "profile": "baseline"},
    )
    step = {"script": "plot.py", "output": "Fig1.png", "theme": "ppt"}
    result = resolve_step_style(step, config, resolved_presets=None)
    assert result["target_format"] == "ppt"


# ---------------------------------------------------------------------------
# validate_config — preset-related errors
# ---------------------------------------------------------------------------

def test_validate_config_invalid_preset_ref():
    config = _base_config(
        presets={"journal": {"target_format": "nature"}},
        figures=[{
            "script": "plot.py",
            "output": "Fig1.png",
            "preset": "nonexistent_preset",
        }],
    )
    errors = validate_config(config)
    assert any("nonexistent_preset" in e for e in errors)


def test_validate_config_preset_unknown_keys():
    config = _base_config(
        presets={"journal": {"target_format": "nature", "unknown_key": "bad"}},
    )
    errors = validate_config(config)
    assert any("unknown_key" in e for e in errors)


def test_validate_config_presets_backward_compat():
    config = _base_config()
    # No presets key at all — must produce zero preset-related errors
    errors = validate_config(config)
    preset_errors = [e for e in errors if "preset" in e.lower()]
    assert preset_errors == []


# ---------------------------------------------------------------------------
# Journal STYLE_PRESETS differentiation (Unit 3)
# ---------------------------------------------------------------------------


def test_acs_tick_direction():
    assert STYLE_PRESETS['acs']['xtick.direction'] == 'out'
    assert STYLE_PRESETS['acs']['ytick.direction'] == 'out'


def test_elsevier_serif_font():
    assert STYLE_PRESETS['elsevier']['font.family'] == 'serif'
    assert STYLE_PRESETS['elsevier']['mathtext.fontset'] == 'dejavuserif'


def test_science_no_box():
    assert STYLE_PRESETS['science']['xtick.top'] is False
    assert STYLE_PRESETS['science']['ytick.right'] is False


def test_rsc_line_weights():
    assert STYLE_PRESETS['rsc']['axes.linewidth'] == 0.6
    assert STYLE_PRESETS['rsc']['lines.linewidth'] == 1.2


def test_journal_presets_differ_from_nature():
    nature = STYLE_PRESETS['nature']
    for journal in ('science', 'acs', 'rsc', 'elsevier'):
        preset = STYLE_PRESETS[journal]
        diffs = {k for k in preset if preset[k] != nature.get(k)}
        assert len(diffs) >= 1, f"{journal} preset has no differences from nature"
