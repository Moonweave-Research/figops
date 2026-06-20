"""Tests for config preset resolution and validation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub_core.config_parser import resolve_presets, resolve_step_style, validate_config
from themes.journal_theme import STYLE_PRESETS, apply_journal_theme


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


def test_validate_config_accepts_nature_surfur_as_official_target_format():
    config = _base_config(
        visual_style={"target_format": "nature_surfur", "font_scale": 1.0, "profile": "baseline"},
    )
    errors = validate_config(config)
    assert errors == []


def test_nature_surfur_theme_loads_as_distinct_project_preset():
    apply_journal_theme("nature_surfur")
    assert "nature_surfur" in STYLE_PRESETS
    assert STYLE_PRESETS["nature_surfur"]["legend.fontsize"] == 6.0
    assert STYLE_PRESETS["nature_surfur"]["xtick.minor.visible"] is False


# ---------------------------------------------------------------------------
# Journal STYLE_PRESETS differentiation (Unit 3)
# ---------------------------------------------------------------------------


def test_acs_tick_direction():
    assert STYLE_PRESETS['acs']['xtick.direction'] == 'out'
    assert STYLE_PRESETS['acs']['ytick.direction'] == 'out'


def test_elsevier_sans_serif_font():
    assert STYLE_PRESETS['elsevier']['font.family'] == 'sans-serif'
    assert STYLE_PRESETS['elsevier']['font.sans-serif'][0] == 'Arial'


def test_science_no_box():
    assert STYLE_PRESETS['science']['xtick.top'] is False
    assert STYLE_PRESETS['science']['ytick.right'] is False


def test_rsc_line_weights():
    assert STYLE_PRESETS['rsc']['axes.linewidth'] == 0.6
    assert STYLE_PRESETS['rsc']['lines.linewidth'] == 1.0


def test_journal_presets_differ_from_nature():
    nature = STYLE_PRESETS['nature']
    for journal in ('science', 'acs', 'rsc', 'elsevier'):
        preset = STYLE_PRESETS[journal]
        diffs = {k for k in preset if preset[k] != nature.get(k)}
        assert len(diffs) >= 1, f"{journal} preset has no differences from nature"


# ---------------------------------------------------------------------------
# Wiley and Cell Press presets (Phase 2)
# ---------------------------------------------------------------------------

def test_wiley_preset_loads():
    apply_journal_theme("wiley")
    assert "wiley" in STYLE_PRESETS
    preset = STYLE_PRESETS["wiley"]
    assert preset["axes.labelsize"] == 7.0
    assert preset["axes.titlesize"] == 7.5
    assert preset["savefig.dpi"] == 600


def test_cell_preset_loads():
    apply_journal_theme("cell")
    assert "cell" in STYLE_PRESETS
    preset = STYLE_PRESETS["cell"]
    assert preset["axes.labelsize"] == 7.0
    assert preset["savefig.dpi"] == 600


def test_wiley_tick_direction():
    assert STYLE_PRESETS["wiley"]["xtick.direction"] == "in"
    assert STYLE_PRESETS["wiley"]["ytick.direction"] == "in"
    assert STYLE_PRESETS["wiley"]["xtick.top"] is True
    assert STYLE_PRESETS["wiley"]["ytick.right"] is True


def test_cell_tick_direction():
    assert STYLE_PRESETS["cell"]["xtick.direction"] == "out"
    assert STYLE_PRESETS["cell"]["ytick.direction"] == "out"
    assert STYLE_PRESETS["cell"]["xtick.top"] is False
    assert STYLE_PRESETS["cell"]["ytick.right"] is False


def test_wiley_line_width():
    assert STYLE_PRESETS["wiley"]["lines.linewidth"] == 1.0
    assert STYLE_PRESETS["wiley"]["axes.linewidth"] == 0.7


def test_cell_line_width():
    assert STYLE_PRESETS["cell"]["lines.linewidth"] == 1.0
    assert STYLE_PRESETS["cell"]["axes.linewidth"] == 0.65
