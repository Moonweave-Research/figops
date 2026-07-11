import json
import os
import tempfile
import unittest
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from hub_core.geometry_diagnostics import diagnose_figure_geometry
from hub_core.scaffold import DEFAULT_DIAGRAM_PY, DEFAULT_PLOT_PY, DEFAULT_PROJECT_CONTEXT_PY
from themes.journal_theme import (
    TIFF_AUTO_PRESETS,
    _active_font_token_sizes,
    apply_journal_theme,
    apply_publication_layout,
    font_tokens,
    mm_to_inch,
    panel_label,
    save_journal_fig,
)
from themes.layout import apply_publication_layout as apply_publication_layout_from_layout_module
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT
from themes.style_profiles import INTERNAL_RESISTANCE_PROFILE, get_render_style_tokens


def _axes_box_mm(fig, ax):
    fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())
    pos = ax.get_position()
    return fig_w_mm * pos.width, fig_h_mm * pos.height


class JournalThemeLayoutTest(unittest.TestCase):
    def setUp(self):
        self._saved_rc = plt.rcParams.copy()

    def tearDown(self):
        plt.rcParams.update(self._saved_rc)

    def test_panel_label_places_readable_corner_label_with_default_box(self):
        fig, ax = plt.subplots()
        try:
            text = panel_label(ax, "n = 12")

            self.assertEqual(text.get_text(), "n = 12")
            self.assertEqual(text.get_position(), (0.03, 0.97))
            self.assertIs(text.get_transform(), ax.transAxes)
            self.assertEqual(text.get_ha(), "left")
            self.assertEqual(text.get_va(), "top")
            self.assertEqual(text.get_zorder(), 20)

            bbox = text.get_bbox_patch()
            self.assertIsNotNone(bbox)
            self.assertEqual(bbox.get_facecolor()[:3], (1.0, 1.0, 1.0))
            self.assertAlmostEqual(bbox.get_alpha(), 0.72)
            self.assertAlmostEqual(bbox.get_linewidth(), 0.0)
        finally:
            plt.close(fig)

    def test_panel_label_supports_corner_presets_and_kw_overrides(self):
        fig, ax = plt.subplots()
        try:
            text = panel_label(ax, "B", loc="lower right", color="#0055aa", box=False, fontsize=9, fontweight="bold")

            self.assertEqual(text.get_position(), (0.97, 0.03))
            self.assertEqual(text.get_ha(), "right")
            self.assertEqual(text.get_va(), "bottom")
            self.assertEqual(text.get_color(), "#0055aa")
            self.assertEqual(text.get_fontsize(), 9)
            self.assertEqual(text.get_fontweight(), "bold")
            self.assertIsNone(text.get_bbox_patch())
        finally:
            plt.close(fig)

    def test_panel_label_rejects_unknown_corner_preset(self):
        fig, ax = plt.subplots()
        try:
            with self.assertRaisesRegex(ValueError, "Unsupported panel_label loc"):
                panel_label(ax, "bad", loc="middle center")
        finally:
            plt.close(fig)

    def test_scaffold_templates_expose_panel_label_helper(self):
        self.assertIn("panel_label", DEFAULT_PLOT_PY)
        self.assertIn("panel_label", DEFAULT_DIAGRAM_PY)

    def test_scaffold_templates_expose_font_tokens(self):
        self.assertIn("font_tokens", DEFAULT_PLOT_PY)
        self.assertIn("font_tokens", DEFAULT_DIAGRAM_PY)
        self.assertIn("FONT", DEFAULT_PLOT_PY)
        self.assertIn("FONT", DEFAULT_DIAGRAM_PY)

    def test_project_context_template_exposes_theme_font_tokens(self):
        self.assertIn("RESEARCH_HUB_PATH", DEFAULT_PROJECT_CONTEXT_PY)
        self.assertIn("theme_font_tokens", DEFAULT_PROJECT_CONTEXT_PY)
        self.assertIn("font_tokens", DEFAULT_PROJECT_CONTEXT_PY)
        self.assertIn("apply_project_theme", DEFAULT_PROJECT_CONTEXT_PY)
        self.assertIn("THEME_PROFILE", DEFAULT_PROJECT_CONTEXT_PY)

    def test_font_tokens_expose_named_role_sizes(self):
        tokens = font_tokens(INTERNAL_STYLE_TARGET_FORMAT)

        self.assertEqual(tokens.tag, 6.0)
        self.assertEqual(tokens.label, 5.0)
        self.assertEqual(tokens.annot, 6.0)
        self.assertEqual(tokens.annotation, tokens.annot)
        self.assertEqual(tokens["legend"], 6.0)
        self.assertEqual(tokens.as_dict()["axis"], 7.0)

    def test_font_tokens_preserve_facade_owned_result_type(self):
        from themes.journal_theme import FontTokens

        tokens = font_tokens("nature")

        self.assertIs(type(tokens), FontTokens)
        self.assertEqual(FontTokens.__module__, "themes.journal_theme")

    def test_science_font_tokens_use_aaas_sans_serif_scale(self):
        tokens = font_tokens("science")

        self.assertEqual(tokens.tag, 8.0)
        self.assertEqual(tokens.label, 7.0)
        self.assertEqual(tokens.annot, 7.0)
        self.assertEqual(tokens.legend, 7.0)
        self.assertEqual(tokens.axis, 7.0)
        self.assertEqual(tokens.tick, 6.5)

    def test_acs_font_tokens_use_readable_sans_serif_scale(self):
        tokens = font_tokens("acs")

        self.assertEqual(tokens.tag, 8.0)
        self.assertEqual(tokens.label, 7.0)
        self.assertEqual(tokens.annot, 7.0)
        self.assertEqual(tokens.legend, 7.0)
        self.assertEqual(tokens.axis, 7.0)
        self.assertEqual(tokens.tick, 6.5)

    def test_wiley_font_tokens_use_readable_sans_serif_scale(self):
        tokens = font_tokens("wiley")

        self.assertEqual(tokens.tag, 8.0)
        self.assertEqual(tokens.label, 7.0)
        self.assertEqual(tokens.annot, 7.0)
        self.assertEqual(tokens.legend, 7.0)
        self.assertEqual(tokens.axis, 7.0)
        self.assertEqual(tokens.tick, 6.5)

    def test_cell_font_tokens_use_readable_sans_serif_scale(self):
        tokens = font_tokens("cell")

        self.assertEqual(tokens.tag, 8.0)
        self.assertEqual(tokens.label, 7.0)
        self.assertEqual(tokens.annot, 7.0)
        self.assertEqual(tokens.legend, 7.0)
        self.assertEqual(tokens.axis, 7.0)
        self.assertEqual(tokens.tick, 6.5)

    def test_rsc_font_tokens_use_readable_sans_serif_scale(self):
        tokens = font_tokens("rsc")

        self.assertEqual(tokens.tag, 8.0)
        self.assertEqual(tokens.label, 7.0)
        self.assertEqual(tokens.annot, 7.0)
        self.assertEqual(tokens.legend, 7.0)
        self.assertEqual(tokens.axis, 7.0)
        self.assertEqual(tokens.tick, 7.0)

    def test_elsevier_font_tokens_use_readable_sans_serif_scale(self):
        tokens = font_tokens("elsevier")

        self.assertEqual(tokens.tag, 8.0)
        self.assertEqual(tokens.label, 7.0)
        self.assertEqual(tokens.annot, 7.0)
        self.assertEqual(tokens.legend, 7.0)
        self.assertEqual(tokens.axis, 7.0)
        self.assertEqual(tokens.tick, 7.0)

    def test_elsevier_render_tokens_use_elsevier_column_and_marker_values(self):
        tokens, meta = get_render_style_tokens("elsevier", "baseline")

        self.assertEqual(meta, {"target_format": "elsevier", "profile": "baseline"})
        self.assertEqual(tokens["figure_width_mm"], 90.0)
        self.assertEqual(tokens["figure_height_mm"], 72.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["single"], 90.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["one_half"], 140.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["double"], 190.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["full"], 190.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["triple"], 190.0)
        self.assertEqual(tokens["main_marker_size"], 3.6)
        self.assertEqual(tokens["facet_marker_size"], 2.8)
        self.assertEqual(tokens["main_marker_edge_width"], 0.6)
        self.assertEqual(tokens["main_line_width"], 1.05)
        self.assertEqual(tokens["timeseries_line_width"], 0.9)
        self.assertEqual(tokens["error_line_width"], 0.8)
        self.assertEqual(tokens["error_cap_size"], 2.2)
        self.assertEqual(tokens["jitter_size"], 13.0)
        self.assertEqual(tokens["jitter_line_width"], 0.6)
        self.assertEqual(tokens["bar_edge_width"], 0.55)
        self.assertEqual(tokens["violin_kde_points"], 192)
        self.assertEqual(tokens["violin_width"], 0.5)
        self.assertEqual(tokens["default_colormap"], "viridis")

    def test_rsc_render_tokens_use_rsc_column_and_marker_values(self):
        tokens, meta = get_render_style_tokens("rsc", "baseline")

        self.assertEqual(meta, {"target_format": "rsc", "profile": "baseline"})
        self.assertEqual(tokens["figure_width_mm"], 83.0)
        self.assertEqual(tokens["figure_height_mm"], 66.4)
        self.assertEqual(tokens["figure_column_widths_mm"]["single"], 83.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["one_half"], 171.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["double"], 171.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["full"], 171.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["triple"], 171.0)
        self.assertEqual(tokens["main_marker_size"], 3.3)
        self.assertEqual(tokens["facet_marker_size"], 2.5)
        self.assertEqual(tokens["main_marker_edge_width"], 0.55)
        self.assertEqual(tokens["main_line_width"], 1.0)
        self.assertEqual(tokens["timeseries_line_width"], 0.8)
        self.assertEqual(tokens["error_line_width"], 0.75)
        self.assertEqual(tokens["error_cap_size"], 2.0)
        self.assertEqual(tokens["jitter_size"], 12.0)
        self.assertEqual(tokens["jitter_line_width"], 0.55)
        self.assertEqual(tokens["bar_edge_width"], 0.5)
        self.assertEqual(tokens["violin_kde_points"], 192)
        self.assertEqual(tokens["violin_width"], 0.5)
        self.assertEqual(tokens["default_colormap"], "viridis")

    def test_cell_render_tokens_use_cell_press_column_and_marker_values(self):
        tokens, meta = get_render_style_tokens("cell", "baseline")

        self.assertEqual(meta, {"target_format": "cell", "profile": "baseline"})
        self.assertEqual(tokens["figure_width_mm"], 85.0)
        self.assertEqual(tokens["figure_height_mm"], 68.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["single"], 85.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["one_half"], 114.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["double"], 174.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["full"], 174.0)
        self.assertEqual(tokens["figure_column_widths_mm"]["triple"], 174.0)
        self.assertEqual(tokens["main_marker_size"], 3.4)
        self.assertEqual(tokens["facet_marker_size"], 2.6)
        self.assertEqual(tokens["main_marker_edge_width"], 0.55)
        self.assertEqual(tokens["main_line_width"], 1.0)
        self.assertEqual(tokens["timeseries_line_width"], 0.85)
        self.assertEqual(tokens["error_line_width"], 0.8)
        self.assertEqual(tokens["error_cap_size"], 2.0)
        self.assertEqual(tokens["jitter_size"], 12.0)
        self.assertEqual(tokens["jitter_line_width"], 0.55)
        self.assertEqual(tokens["bar_edge_width"], 0.55)
        self.assertEqual(tokens["violin_kde_points"], 192)
        self.assertEqual(tokens["violin_width"], 0.5)
        self.assertEqual(tokens["default_colormap"], "viridis")

    def test_existing_track_render_tokens_are_unchanged(self):
        expected = {
            "nature": {
                "figure_width_mm": 88.0,
                "figure_height_mm": 71.0,
                "figure_column_widths_mm": {"single": 88.0, "double": 180.0, "full": 180.0},
                "main_marker_size": 3.2,
                "facet_marker_size": 2.4,
                "axis_marker_margin_fraction": 0.06,
                "facet_axis_marker_margin_fraction": 0.16,
                "violin_kde_points": 256,
                "violin_kde_bw_method": "scott",
                "violin_width": 0.52,
            },
            "science": {
                "figure_width_mm": 57.0,
                "figure_height_mm": 45.6,
                "figure_column_widths_mm": {"single": 57.0, "double": 121.0, "full": 184.0, "triple": 184.0},
                "main_marker_size": 3.0,
                "facet_marker_size": 2.2,
                "main_marker_edge_width": 0.5,
                "main_line_width": 0.9,
                "timeseries_line_width": 0.75,
                "error_line_width": 0.7,
                "error_cap_size": 1.8,
                "jitter_size": 10.0,
                "jitter_line_width": 0.5,
                "bar_edge_width": 0.45,
                "violin_kde_points": 192,
                "violin_width": 0.48,
                "default_colormap": "viridis",
            },
            "acs": {
                "figure_width_mm": 84.67,
                "figure_height_mm": 67.736,
                "figure_column_widths_mm": {"single": 84.67, "double": 177.8, "full": 177.8},
                "main_marker_size": 3.4,
                "facet_marker_size": 2.6,
                "main_marker_edge_width": 0.55,
                "main_line_width": 1.0,
                "timeseries_line_width": 0.8,
                "error_line_width": 0.75,
                "error_cap_size": 2.0,
                "jitter_size": 12.0,
                "jitter_line_width": 0.55,
                "bar_edge_width": 0.5,
                "violin_kde_points": 192,
                "violin_width": 0.5,
                "default_colormap": "viridis",
            },
            "wiley": {
                "figure_width_mm": 85.0,
                "figure_height_mm": 68.0,
                "figure_column_widths_mm": {"single": 85.0, "double": 178.0, "full": 178.0},
                "main_marker_size": 3.5,
                "facet_marker_size": 2.7,
                "main_marker_edge_width": 0.55,
                "main_line_width": 1.0,
                "timeseries_line_width": 0.85,
                "error_line_width": 0.8,
                "error_cap_size": 2.0,
                "jitter_size": 12.5,
                "jitter_line_width": 0.55,
                "bar_edge_width": 0.55,
                "violin_kde_points": 192,
                "violin_width": 0.5,
                "default_colormap": "viridis",
            },
            "cell": {
                "figure_width_mm": 85.0,
                "figure_height_mm": 68.0,
                "figure_column_widths_mm": {
                    "single": 85.0,
                    "one_half": 114.0,
                    "double": 174.0,
                    "full": 174.0,
                    "triple": 174.0,
                },
                "main_marker_size": 3.4,
                "facet_marker_size": 2.6,
                "main_marker_edge_width": 0.55,
                "main_line_width": 1.0,
                "timeseries_line_width": 0.85,
                "error_line_width": 0.8,
                "error_cap_size": 2.0,
                "jitter_size": 12.0,
                "jitter_line_width": 0.55,
                "bar_edge_width": 0.55,
                "violin_kde_points": 192,
                "violin_width": 0.5,
                "default_colormap": "viridis",
            },
            "rsc": {
                "figure_width_mm": 83.0,
                "figure_height_mm": 66.4,
                "figure_column_widths_mm": {
                    "single": 83.0,
                    "one_half": 171.0,
                    "double": 171.0,
                    "full": 171.0,
                    "triple": 171.0,
                },
                "main_marker_size": 3.3,
                "facet_marker_size": 2.5,
                "main_marker_edge_width": 0.55,
                "main_line_width": 1.0,
                "timeseries_line_width": 0.8,
                "error_line_width": 0.75,
                "error_cap_size": 2.0,
                "jitter_size": 12.0,
                "jitter_line_width": 0.55,
                "bar_edge_width": 0.5,
                "violin_kde_points": 192,
                "violin_width": 0.5,
                "default_colormap": "viridis",
            },
        }

        for target_format, expected_tokens in expected.items():
            with self.subTest(target_format=target_format):
                tokens, meta = get_render_style_tokens(target_format, "baseline")

                self.assertEqual(meta, {"target_format": target_format, "profile": "baseline"})
                for key, expected_value in expected_tokens.items():
                    self.assertEqual(tokens[key], expected_value)

    def test_apply_science_theme_uses_distinct_sans_serif_rc_values(self):
        saved_rc = plt.rcParams.copy()
        try:
            apply_journal_theme("science")

            self.assertEqual(plt.rcParams["font.family"], ["sans-serif"])
            self.assertEqual(plt.rcParams["font.sans-serif"][0], "Helvetica")
            self.assertEqual(plt.rcParams["font.size"], 7.0)
            self.assertEqual(plt.rcParams["axes.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["legend.fontsize"], 7.0)
            self.assertEqual(plt.rcParams["xtick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["ytick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["lines.linewidth"], 0.9)
            self.assertEqual(plt.rcParams["lines.markersize"], 3.0)
            self.assertFalse(plt.rcParams["xtick.top"])
            self.assertFalse(plt.rcParams["ytick.right"])
        finally:
            plt.rcParams.update(saved_rc)

    def test_apply_acs_theme_uses_distinct_sans_serif_rc_values(self):
        saved_rc = plt.rcParams.copy()
        try:
            apply_journal_theme("acs")

            self.assertEqual(plt.rcParams["font.family"], ["sans-serif"])
            self.assertEqual(plt.rcParams["font.sans-serif"][0], "Helvetica")
            self.assertEqual(plt.rcParams["font.size"], 7.0)
            self.assertEqual(plt.rcParams["axes.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["legend.fontsize"], 7.0)
            self.assertEqual(plt.rcParams["xtick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["ytick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["axes.linewidth"], 0.6)
            self.assertEqual(plt.rcParams["lines.linewidth"], 1.0)
            self.assertEqual(plt.rcParams["lines.markersize"], 3.4)
            self.assertEqual(plt.rcParams["lines.markeredgewidth"], 0.55)
            self.assertEqual(plt.rcParams["xtick.direction"], "out")
            self.assertEqual(plt.rcParams["ytick.direction"], "out")
        finally:
            plt.rcParams.update(saved_rc)

    def test_apply_wiley_theme_uses_distinct_sans_serif_rc_values(self):
        saved_rc = plt.rcParams.copy()
        try:
            apply_journal_theme("wiley")

            self.assertEqual(plt.rcParams["font.family"], ["sans-serif"])
            self.assertEqual(plt.rcParams["font.sans-serif"][0], "Helvetica")
            self.assertEqual(plt.rcParams["font.size"], 7.0)
            self.assertEqual(plt.rcParams["axes.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["legend.fontsize"], 7.0)
            self.assertEqual(plt.rcParams["xtick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["ytick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["axes.linewidth"], 0.7)
            self.assertEqual(plt.rcParams["lines.linewidth"], 1.0)
            self.assertEqual(plt.rcParams["lines.markersize"], 3.5)
            self.assertEqual(plt.rcParams["lines.markeredgewidth"], 0.55)
            self.assertEqual(plt.rcParams["xtick.direction"], "in")
            self.assertEqual(plt.rcParams["ytick.direction"], "in")
        finally:
            plt.rcParams.update(saved_rc)

    def test_apply_cell_theme_uses_distinct_sans_serif_rc_values(self):
        saved_rc = plt.rcParams.copy()
        try:
            apply_journal_theme("cell")

            self.assertEqual(plt.rcParams["font.family"], ["sans-serif"])
            self.assertEqual(plt.rcParams["font.sans-serif"][0], "Arial")
            self.assertEqual(plt.rcParams["font.size"], 7.0)
            self.assertEqual(plt.rcParams["axes.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["legend.fontsize"], 7.0)
            self.assertEqual(plt.rcParams["xtick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["ytick.labelsize"], 6.5)
            self.assertEqual(plt.rcParams["axes.linewidth"], 0.65)
            self.assertEqual(plt.rcParams["lines.linewidth"], 1.0)
            self.assertEqual(plt.rcParams["lines.markersize"], 3.4)
            self.assertEqual(plt.rcParams["lines.markeredgewidth"], 0.55)
            self.assertEqual(plt.rcParams["xtick.direction"], "out")
            self.assertEqual(plt.rcParams["ytick.direction"], "out")
            self.assertFalse(plt.rcParams["xtick.top"])
            self.assertFalse(plt.rcParams["ytick.right"])
        finally:
            plt.rcParams.update(saved_rc)

    def test_apply_rsc_theme_uses_distinct_sans_serif_rc_values(self):
        saved_rc = plt.rcParams.copy()
        try:
            apply_journal_theme("rsc")

            self.assertEqual(plt.rcParams["font.family"], ["sans-serif"])
            self.assertEqual(plt.rcParams["font.sans-serif"][0], "Arial")
            self.assertEqual(plt.rcParams["font.size"], 7.0)
            self.assertEqual(plt.rcParams["axes.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["legend.fontsize"], 7.0)
            self.assertEqual(plt.rcParams["xtick.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["ytick.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["axes.linewidth"], 0.6)
            self.assertEqual(plt.rcParams["lines.linewidth"], 1.0)
            self.assertEqual(plt.rcParams["lines.markersize"], 3.3)
            self.assertEqual(plt.rcParams["lines.markeredgewidth"], 0.55)
            self.assertEqual(plt.rcParams["xtick.direction"], "out")
            self.assertEqual(plt.rcParams["ytick.direction"], "out")
        finally:
            plt.rcParams.update(saved_rc)

    def test_apply_elsevier_theme_uses_distinct_sans_serif_rc_values(self):
        saved_rc = plt.rcParams.copy()
        try:
            apply_journal_theme("elsevier")

            self.assertEqual(plt.rcParams["font.family"], ["sans-serif"])
            self.assertEqual(plt.rcParams["font.sans-serif"][0], "Arial")
            self.assertEqual(plt.rcParams["font.size"], 7.0)
            self.assertEqual(plt.rcParams["axes.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["legend.fontsize"], 7.0)
            self.assertEqual(plt.rcParams["xtick.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["ytick.labelsize"], 7.0)
            self.assertEqual(plt.rcParams["axes.linewidth"], 0.65)
            self.assertEqual(plt.rcParams["lines.linewidth"], 1.05)
            self.assertEqual(plt.rcParams["lines.markersize"], 3.6)
            self.assertEqual(plt.rcParams["lines.markeredgewidth"], 0.6)
            self.assertEqual(plt.rcParams["xtick.direction"], "out")
            self.assertEqual(plt.rcParams["ytick.direction"], "out")
        finally:
            plt.rcParams.update(saved_rc)

    def test_apply_theme_clamps_subfloor_font_and_line_values_with_warning(self):
        saved_rc = plt.rcParams.copy()
        try:
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                apply_journal_theme("science", font_scale=0.1)

            messages = [str(item.message) for item in captured]
            self.assertTrue(any("journal compliance" in message and "font" in message for message in messages))
            self.assertTrue(any("journal compliance" in message and "line" in message for message in messages))
            self.assertEqual(plt.rcParams["font.size"], 5.0)
            self.assertEqual(plt.rcParams["axes.labelsize"], 5.0)
            self.assertEqual(plt.rcParams["legend.fontsize"], 5.0)
            self.assertEqual(plt.rcParams["xtick.labelsize"], 5.0)
            self.assertEqual(plt.rcParams["ytick.labelsize"], 5.0)
            self.assertEqual(plt.rcParams["lines.linewidth"], 0.5)
            self.assertEqual(plt.rcParams["axes.linewidth"], 0.5)
            self.assertEqual(plt.rcParams["lines.markeredgewidth"], 0.5)
        finally:
            plt.rcParams.update(saved_rc)

    def test_font_tokens_apply_profile_font_overrides(self):
        tokens = font_tokens(INTERNAL_STYLE_TARGET_FORMAT, profile_name=INTERNAL_RESISTANCE_PROFILE)

        self.assertEqual(tokens.tag, 8.5)
        self.assertEqual(tokens.label, 7.5)
        self.assertEqual(tokens.annot, 7.5)
        self.assertEqual(tokens.axis, 7.5)
        self.assertEqual(tokens.legend, 6.5)
        self.assertEqual(tokens.tick, 6.5)

    def test_active_font_token_sizes_do_not_leak_default_font_size(self):
        apply_journal_theme("ppt")

        self.assertNotIn(10.0, _active_font_token_sizes())

    def test_apply_journal_theme_passes_active_tokens_to_diagnostics(self):
        apply_journal_theme(INTERNAL_STYLE_TARGET_FORMAT)
        fig, ax = plt.subplots()
        ax.text(0.2, 0.2, "token", fontsize=font_tokens(INTERNAL_STYLE_TARGET_FORMAT).label)
        ax.text(0.4, 0.4, "drift", fontsize=5.5)
        try:
            with tempfile.TemporaryDirectory(prefix="journal_tokens_") as tmpdir:
                out_path = Path(tmpdir) / "tokens.png"
                prior = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
                os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = str(Path(tmpdir) / "geometry.json")
                try:
                    save_journal_fig(fig, out_path, dpi=150)
                finally:
                    if prior is None:
                        os.environ.pop("GEOMETRY_DIAGNOSTICS_OUT", None)
                    else:
                        os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = prior
                payload = Path(tmpdir, "geometry.json").read_text(encoding="utf-8")
                self.assertIn("font_size_token_drift", payload)
                self.assertIn("drift", payload)
        finally:
            plt.close(fig)

    def test_apply_journal_theme_passes_journal_compliance_to_diagnostics(self):
        apply_journal_theme("science")
        fig, ax = plt.subplots(figsize=(mm_to_inch(57.0), mm_to_inch(45.6)))
        ax.plot([0, 1, 2], [0, 1, 0], label="A")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.legend()
        try:
            with tempfile.TemporaryDirectory(prefix="journal_compliance_") as tmpdir:
                out_path = Path(tmpdir) / "science.png"
                sidecar_path = Path(tmpdir) / "geometry.json"
                prior = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
                os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = str(sidecar_path)
                try:
                    save_journal_fig(fig, out_path, dpi=150)
                finally:
                    if prior is None:
                        os.environ.pop("GEOMETRY_DIAGNOSTICS_OUT", None)
                    else:
                        os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = prior
                payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
                compliance = next(check for check in payload["checks"] if check["name"] == "journal_compliance")
                self.assertTrue(compliance["passed"])
                self.assertEqual(compliance["data"]["target_format"], "science")
                self.assertEqual(compliance["data"]["min_font_size_pt"], 5.0)
                self.assertEqual(compliance["data"]["min_line_width_pt"], 0.5)
                self.assertEqual(compliance["data"]["max_figure_height_mm"], 234.0)
        finally:
            plt.close(fig)

    def test_non_baseline_profile_clamps_and_reports_journal_compliance(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            apply_journal_theme("science", font_scale=0.1, profile_name=INTERNAL_RESISTANCE_PROFILE)

        self.assertGreaterEqual(plt.rcParams["font.size"], 5.0)
        self.assertGreaterEqual(plt.rcParams["lines.linewidth"], 0.5)
        self.assertTrue(any("journal compliance" in str(item.message) for item in caught))

        fig, ax = plt.subplots(figsize=(mm_to_inch(57.0), mm_to_inch(45.6)))
        ax.plot([0, 1, 2], [0, 1, 0], label="A")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.legend()
        try:
            with tempfile.TemporaryDirectory(prefix="journal_compliance_profile_") as tmpdir:
                out_path = Path(tmpdir) / "science.png"
                sidecar_path = Path(tmpdir) / "geometry.json"
                prior = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
                os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = str(sidecar_path)
                try:
                    save_journal_fig(fig, out_path, dpi=150)
                finally:
                    if prior is None:
                        os.environ.pop("GEOMETRY_DIAGNOSTICS_OUT", None)
                    else:
                        os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = prior
                payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
                compliance = next(check for check in payload["checks"] if check["name"] == "journal_compliance")
                self.assertTrue(compliance["passed"])
                self.assertEqual(compliance["data"]["target_format"], "science")
                self.assertEqual(compliance["data"]["min_font_size_pt"], 5.0)
                self.assertEqual(compliance["data"]["min_line_width_pt"], 0.5)
        finally:
            plt.close(fig)

    def test_save_journal_fig_clamps_explicit_subfloor_artists_before_save(self):
        apply_journal_theme("science")
        fig, ax = plt.subplots(figsize=(mm_to_inch(57.0), mm_to_inch(45.6)))
        line = ax.plot([0, 1, 2], [0, 1, 0], linewidth=0.1, label="thin")[0]
        text = ax.text(0.5, 0.5, "tiny", fontsize=2.0)
        try:
            with tempfile.TemporaryDirectory(prefix="journal_artist_clamp_") as tmpdir:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    save_journal_fig(fig, Path(tmpdir) / "clamped.png", dpi=150)

            self.assertEqual(text.get_fontsize(), 5.0)
            self.assertEqual(line.get_linewidth(), 0.5)
            self.assertTrue(
                any("journal compliance" in str(item.message) and "artist" in str(item.message) for item in caught)
            )
        finally:
            plt.close(fig)

    def test_profile_font_overrides_are_allowed_tokens(self):
        apply_journal_theme(INTERNAL_STYLE_TARGET_FORMAT, profile_name=INTERNAL_RESISTANCE_PROFILE)
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1], label="series")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.legend()
        try:
            result = diagnose_figure_geometry(
                fig,
                [ax],
                layout_locked=False,
                font_token_sizes=list(
                    font_tokens(
                        INTERNAL_STYLE_TARGET_FORMAT,
                        profile_name=INTERNAL_RESISTANCE_PROFILE,
                    ).as_dict().values()
                ),
            )
            drift = next(check for check in result["checks"] if check["name"] == "font_size_token_drift")
            self.assertTrue(drift["passed"])
        finally:
            plt.close(fig)

    def test_standard_layout_preserves_absolute_box_size_across_initial_canvas_sizes(self):
        initial_heights_mm = (70.0, 85.0)

        for initial_height_mm in initial_heights_mm:
            fig, ax = plt.subplots(figsize=(mm_to_inch(89.0), mm_to_inch(initial_height_mm)))
            try:
                apply_publication_layout("standard", fig=fig, target_format="nature")
                box_w_mm, box_h_mm = _axes_box_mm(fig, ax)
                fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())

                self.assertAlmostEqual(fig_w_mm, 89.0, places=1)
                self.assertAlmostEqual(fig_h_mm, 75.0, places=1)
                self.assertAlmostEqual(box_w_mm, 70.0, places=1)
                self.assertAlmostEqual(box_h_mm, 55.0, places=1)
            finally:
                plt.close(fig)

    def test_layout_module_publication_layout_matches_journal_theme_reexport(self):
        fig, ax = plt.subplots(figsize=(mm_to_inch(89.0), mm_to_inch(70.0)))
        try:
            result = apply_publication_layout_from_layout_module("standard", fig=fig, target_format="nature")
            box_w_mm, box_h_mm = _axes_box_mm(fig, ax)

            self.assertAlmostEqual(result["figure_width_mm"], 89.0, places=1)
            self.assertAlmostEqual(result["figure_height_mm"], 75.0, places=1)
            self.assertAlmostEqual(box_w_mm, 70.0, places=1)
            self.assertAlmostEqual(box_h_mm, 55.0, places=1)
            self.assertIs(apply_publication_layout, apply_publication_layout_from_layout_module)
        finally:
            plt.close(fig)

    def test_top_outside_layout_preserves_absolute_box_size_across_initial_canvas_sizes(self):
        initial_heights_mm = (70.0, 95.0)

        for initial_height_mm in initial_heights_mm:
            fig, ax = plt.subplots(figsize=(mm_to_inch(89.0), mm_to_inch(initial_height_mm)))
            try:
                apply_publication_layout("top_outside", fig=fig, target_format="nature")
                box_w_mm, box_h_mm = _axes_box_mm(fig, ax)
                fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())

                self.assertAlmostEqual(fig_w_mm, 89.0, places=1)
                self.assertAlmostEqual(fig_h_mm, 87.0, places=1)
                self.assertAlmostEqual(box_w_mm, 70.0, places=1)
                self.assertAlmostEqual(box_h_mm, 55.0, places=1)
            finally:
                plt.close(fig)

    def test_ppt_layout_keeps_legacy_relative_behavior(self):
        fig, ax = plt.subplots(figsize=(6, 4))
        try:
            apply_publication_layout("right_outside", fig=fig, target_format="ppt")
            self.assertAlmostEqual(fig.subplotpars.right, 0.75, places=2)
            self.assertFalse(hasattr(fig, "_graph_hub_layout_lock"))
        finally:
            plt.close(fig)

    def test_save_journal_fig_disables_tight_bbox_for_locked_layout(self):
        fig, ax = plt.subplots(figsize=(mm_to_inch(89.0), mm_to_inch(75.0)))
        try:
            apply_publication_layout("standard", fig=fig, target_format="nature")
            with tempfile.TemporaryDirectory(prefix="journal_save_") as tmpdir:
                out_path = Path(tmpdir) / "layout_locked.png"
                save_journal_fig(fig, out_path, dpi=600)
                with Image.open(out_path) as saved:
                    self.assertEqual(saved.size, (2102, 1771))
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_nudges_overlapping_text(self):
        fig, ax = plt.subplots()
        ax.scatter([0.5], [0.5], s=300)
        text = ax.text(0.5, 0.5, "S70", ha="center", va="center")
        try:
            before = text.get_position()
            with tempfile.TemporaryDirectory(prefix="journal_declutter_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            after = text.get_position()
            self.assertNotEqual(before, after)
            fig.canvas.draw()
            check = next(
                c
                for c in diagnose_figure_geometry(fig, [ax], layout_locked=False)["checks"]
                if c["name"] == "artist_overlaps"
            )
            self.assertTrue(check["passed"])
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_adds_leader_for_text_marker_collision(self):
        fig, ax = plt.subplots()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.scatter([0.5], [0.5], s=300)
        text = ax.text(0.5, 0.5, "S70", ha="center", va="center")
        try:
            with tempfile.TemporaryDirectory(prefix="journal_declutter_leader_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            self.assertEqual(text._graph_hub_leader_target_data, (0.5, 0.5))
            self.assertTrue(any(getattr(patch, "_graph_hub_leader_patch", False) for patch in ax.patches))
            fig.canvas.draw()
            check = next(
                c
                for c in diagnose_figure_geometry(fig, [ax], layout_locked=False)["checks"]
                if c["name"] == "artist_overlaps"
            )
            self.assertTrue(check["passed"])
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_targets_nearest_competing_marker(self):
        fig, ax = plt.subplots()
        ax.set_xlim(0.48, 0.58)
        ax.set_ylim(0.48, 0.52)
        ax.scatter([0.50, 0.56], [0.50, 0.50], s=1500)
        text = ax.text(0.56, 0.5, "S75", ha="center", va="center")
        try:
            with tempfile.TemporaryDirectory(prefix="journal_declutter_competing_marker_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            target_x, target_y = text._graph_hub_leader_target_data
            self.assertAlmostEqual(target_x, 0.56, places=2)
            self.assertAlmostEqual(target_y, 0.50, places=2)
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_retargets_stale_leader_metadata(self):
        fig, ax = plt.subplots()
        ax.set_xlim(0.48, 0.58)
        ax.set_ylim(0.48, 0.52)
        ax.scatter([0.50, 0.56], [0.50, 0.50], s=1500)
        text = ax.text(0.56, 0.5, "S75", ha="center", va="center")
        text._graph_hub_leader_target_data = (0.50, 0.50)
        try:
            with tempfile.TemporaryDirectory(prefix="journal_declutter_stale_marker_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            target_x, target_y = text._graph_hub_leader_target_data
            self.assertAlmostEqual(target_x, 0.56, places=2)
            self.assertAlmostEqual(target_y, 0.50, places=2)
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_does_not_move_unrelated_repeated_label(self):
        fig, ax = plt.subplots()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.scatter([0.2], [0.2], s=300)
        colliding = ax.text(0.2, 0.2, "S70", ha="center", va="center")
        unrelated = ax.text(0.8, 0.8, "S70", ha="center", va="center")
        try:
            before_colliding = colliding.get_position()
            before_unrelated = unrelated.get_position()
            with tempfile.TemporaryDirectory(prefix="journal_declutter_repeat_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            self.assertNotEqual(before_colliding, colliding.get_position())
            self.assertEqual(before_unrelated, unrelated.get_position())
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_nudges_clipped_text_inside_axes(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        text = ax.text(1.02, 0.5, "S75", ha="left", va="center")
        try:
            before = text.get_position()
            with tempfile.TemporaryDirectory(prefix="journal_declutter_clip_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            self.assertNotEqual(before, text.get_position())
            fig.canvas.draw()
            check = next(
                c
                for c in diagnose_figure_geometry(fig, [ax], layout_locked=False)["checks"]
                if c["name"] == "text_axis_edge_proximity"
            )
            self.assertTrue(check["passed"])
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_nudges_text_off_line(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.plot([0.1, 0.9], [0.5, 0.5], linewidth=4.0)
        text = ax.text(0.5, 0.5, "line label", ha="center", va="center")
        try:
            before = text.get_position()
            with tempfile.TemporaryDirectory(prefix="journal_declutter_line_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            self.assertNotEqual(before, text.get_position())
            fig.canvas.draw()
            check = next(
                c
                for c in diagnose_figure_geometry(fig, [ax], layout_locked=False)["checks"]
                if c["name"] == "artist_overlaps"
            )
            self.assertTrue(check["passed"])
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_separates_coincident_text_labels(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        first = ax.text(0.5, 0.5, "A", ha="center", va="center")
        second = ax.text(0.5, 0.5, "B", ha="center", va="center")
        try:
            with tempfile.TemporaryDirectory(prefix="journal_declutter_coincident_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            self.assertNotEqual(first.get_position(), second.get_position())
            fig.canvas.draw()
            check = next(
                c
                for c in diagnose_figure_geometry(fig, [ax], layout_locked=False)["checks"]
                if c["name"] == "artist_overlaps"
            )
            self.assertTrue(check["passed"])
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_preserves_axes_coordinate_panel_text(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        panel_label = ax.text(-0.08, 1.12, "a)", transform=ax.transAxes, ha="right", va="bottom")
        try:
            before = panel_label.get_position()
            with tempfile.TemporaryDirectory(prefix="journal_declutter_panel_") as tmpdir:
                save_journal_fig(fig, Path(tmpdir) / "declutter.png", auto_declutter=True, dpi=150)

            self.assertEqual(before, panel_label.get_position())
        finally:
            plt.close(fig)

    def test_save_journal_fig_tiff_companion(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        try:
            with tempfile.TemporaryDirectory(prefix="journal_tiff_") as tmpdir:
                pdf_path = Path(tmpdir) / "figure.pdf"
                save_journal_fig(fig, pdf_path, companion_formats=("png", "tiff"))

                tiff_path = pdf_path.with_suffix(".tiff")
                png_path = pdf_path.with_suffix(".png")
                self.assertTrue(tiff_path.exists(), "TIFF companion not created")
                self.assertTrue(png_path.exists(), "PNG companion not created")
                self.assertGreater(tiff_path.stat().st_size, 1024, "TIFF file too small")
        finally:
            plt.close(fig)

    def test_save_journal_fig_no_tiff_by_default(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        try:
            with tempfile.TemporaryDirectory(prefix="journal_notiff_") as tmpdir:
                pdf_path = Path(tmpdir) / "figure.pdf"
                save_journal_fig(fig, pdf_path)

                tiff_path = pdf_path.with_suffix(".tiff")
                png_path = pdf_path.with_suffix(".png")
                self.assertFalse(tiff_path.exists(), "TIFF should not be created by default")
                self.assertTrue(png_path.exists(), "PNG companion should exist by default")
        finally:
            plt.close(fig)

    def test_tiff_companion_generated_with_png(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        try:
            with tempfile.TemporaryDirectory(prefix="journal_tiff_auto_") as tmpdir:
                png_path = Path(tmpdir) / "figure.png"
                save_journal_fig(fig, png_path, preset="nature", dpi=150)

                tiff_path = png_path.with_suffix(".tiff")
                self.assertTrue(tiff_path.exists(), "TIFF companion not created for nature preset")
                self.assertGreater(tiff_path.stat().st_size, 1024, "TIFF file too small")
        finally:
            plt.close(fig)

    def test_tiff_companion_generated_for_internal_style(self):
        self.assertIn(INTERNAL_STYLE_TARGET_FORMAT, TIFF_AUTO_PRESETS)
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        try:
            with tempfile.TemporaryDirectory(prefix="journal_tiff_surfur_") as tmpdir:
                png_path = Path(tmpdir) / "figure.png"
                save_journal_fig(fig, png_path, preset=INTERNAL_STYLE_TARGET_FORMAT, dpi=150)

                tiff_path = png_path.with_suffix(".tiff")
                self.assertTrue(tiff_path.exists(), "TIFF companion not created for internal preset")
                self.assertGreater(tiff_path.stat().st_size, 1024, "TIFF file too small")
        finally:
            plt.close(fig)

    def test_tiff_companion_skipped_for_ppt(self):
        self.assertNotIn("ppt", TIFF_AUTO_PRESETS)
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        try:
            with tempfile.TemporaryDirectory(prefix="journal_tiff_ppt_") as tmpdir:
                png_path = Path(tmpdir) / "figure.png"
                save_journal_fig(fig, png_path, preset="ppt", dpi=150)

                tiff_path = png_path.with_suffix(".tiff")
                self.assertFalse(tiff_path.exists(), "TIFF should not be created for ppt preset")
        finally:
            plt.close(fig)

    def test_tiff_companion_opt_out(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        try:
            with tempfile.TemporaryDirectory(prefix="journal_tiff_optout_") as tmpdir:
                png_path = Path(tmpdir) / "figure.png"
                save_journal_fig(fig, png_path, preset="nature", tiff_companion=False, dpi=150)

                tiff_path = png_path.with_suffix(".tiff")
                self.assertFalse(tiff_path.exists(), "TIFF should not be created when tiff_companion=False")
        finally:
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
