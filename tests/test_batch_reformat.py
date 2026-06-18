"""Tests for batch journal reformat utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hub_core.batch_reformat import batch_reformat_figures, patch_target_format
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

    def test_overrides_diagram_theme(self):
        config = self._base_config()
        config["diagrams"] = [
            {"id": "D1", "script": "diagram.py", "output": "results/diagrams/D1.png", "theme": "nature"}
        ]

        patched = patch_target_format(config, "science")

        assert patched["diagrams"][0]["theme"] == "science"


def test_batch_reformat_rerenders_figures_and_diagrams(tmp_path):
    project_dir = tmp_path / "project"
    (project_dir / "results" / "figures").mkdir(parents=True)
    (project_dir / "results" / "diagrams").mkdir(parents=True)
    figure_output = project_dir / "results" / "figures" / "Fig1.png"
    diagram_output = project_dir / "results" / "diagrams" / "Diagram1.png"

    config = {
        "visual_style": {"target_format": "nature"},
        "figures": [{"id": "Fig1", "script": "plot.py", "output": "results/figures/Fig1.png", "theme": "nature"}],
        "diagrams": [
            {"id": "Diagram1", "script": "diagram.py", "output": "results/diagrams/Diagram1.png", "theme": "nature"}
        ],
    }

    def fake_run_plots(*args, **kwargs):
        figure_output.write_text("figure\n", encoding="utf-8")
        return True

    def fake_run_diagrams(*args, **kwargs):
        diagram_output.write_text("diagram\n", encoding="utf-8")
        return True

    with (
        patch(
            "hub_core.cache_manager.load_build_state",
            return_value=({}, str(project_dir / ".build_state.json")),
        ),
        patch("hub_core.process_runner.run_plots", side_effect=fake_run_plots) as run_plots,
        patch("hub_core.process_runner.run_diagrams", side_effect=fake_run_diagrams) as run_diagrams,
    ):
        result = batch_reformat_figures(str(project_dir), "science", config, hub_path=str(Path.cwd()))

    assert result.success is True
    assert result.figures_regenerated == 2
    assert str(figure_output) in result.output_paths
    assert str(diagram_output) in result.output_paths
    run_plots.assert_called_once()
    run_diagrams.assert_called_once()


def test_batch_reformat_passes_dict_build_state_not_tuple(tmp_path):
    """Regression: load_build_state returns (state, path). batch_reformat must unpack it
    and pass a dict build_state to the runners; passing the raw tuple crashes
    record_step_state after figures are already written. load_build_state is NOT mocked
    here so the real tuple return shape is exercised."""
    from hub_core.cache_manager import record_step_state

    project_dir = tmp_path / "project"
    (project_dir / "results" / "figures").mkdir(parents=True)
    figure_output = project_dir / "results" / "figures" / "Fig1.png"

    config = {
        "visual_style": {"target_format": "nature"},
        "figures": [{"id": "Fig1", "script": "plot.py", "output": "results/figures/Fig1.png"}],
    }

    captured: dict = {}

    def fake_run_plots(*args, **kwargs):
        captured["build_state"] = kwargs["build_state"]
        figure_output.write_text("figure\n", encoding="utf-8")
        # Mimic what the real runner does: a tuple build_state crashes here.
        record_step_state(kwargs["build_state"], "figures", "Fig1", "sig", [], kwargs["config_hash"])
        return True

    with patch("hub_core.process_runner.run_plots", side_effect=fake_run_plots):
        result = batch_reformat_figures(str(project_dir), "science", config, hub_path=str(Path.cwd()))

    assert result.success is True
    assert isinstance(captured["build_state"], dict)
