"""Tests for batch journal reformat utilities."""

from __future__ import annotations

import pytest

from hub_core.batch_reformat import patch_target_format
from hub_core.config_parser import ALLOWED_TARGET_FORMATS


class TestPatchTargetFormat:
    def _base_config(self) -> dict:
        return {
            "project": {"name": "Test", "version": "1.0.0"},
            "visual_style": {"target_format": "nature", "font_scale": 1.0},
            "figures": [
                {"id": "Fig1", "script": "plot.py", "output": "results/figures/Fig1.png", "theme": "nature"},
                {"id": "Fig2", "script": "plot2.py", "output": "results/figures/Fig2.png"},
            ],
            "presets": {
                "default_style": {"target_format": "nature", "font_scale": 1.0},
            },
        }

    def test_overrides_visual_style(self):
        patched = patch_target_format(self._base_config(), "science")
        assert patched["visual_style"]["target_format"] == "science"

    def test_overrides_figure_theme(self):
        patched = patch_target_format(self._base_config(), "science")
        assert patched["figures"][0]["theme"] == "science"

    def test_preserves_figures_without_theme(self):
        patched = patch_target_format(self._base_config(), "science")
        assert "theme" not in patched["figures"][1]

    def test_overrides_preset_target_format(self):
        patched = patch_target_format(self._base_config(), "acs")
        assert patched["presets"]["default_style"]["target_format"] == "acs"

    def test_does_not_mutate_original(self):
        original = self._base_config()
        patch_target_format(original, "science")
        assert original["visual_style"]["target_format"] == "nature"

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Unknown target format"):
            patch_target_format(self._base_config(), "invalid_journal")

    def test_all_allowed_formats_accepted(self):
        for fmt in ALLOWED_TARGET_FORMATS:
            patched = patch_target_format(self._base_config(), fmt)
            assert patched["visual_style"]["target_format"] == fmt

    def test_new_formats_accepted(self):
        for fmt in ("acs", "rsc", "elsevier"):
            patched = patch_target_format(self._base_config(), fmt)
            assert patched["visual_style"]["target_format"] == fmt
