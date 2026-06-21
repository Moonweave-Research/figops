"""Unit tests for themes/style_profiles.py — multi-channel encoding and profile resolution."""

import unittest

from themes.style_profiles import (
    HATCH_CYCLE,
    LINESTYLE_CYCLE,
    MARKER_CYCLE,
    get_profile_tokens,
    get_render_style_tokens,
    get_series_style,
    list_profiles,
    resolve_profile_name,
)


class TestSeriesStyle(unittest.TestCase):
    """Tests for get_series_style and cycle constants."""

    def test_first_series_defaults(self):
        sty = get_series_style(0)
        self.assertEqual(sty["marker"], "o")
        self.assertEqual(sty["linestyle"], "-")
        self.assertEqual(sty["hatch"], "//")

    def test_second_series_differs(self):
        s0 = get_series_style(0)
        s1 = get_series_style(1)
        self.assertNotEqual(s0["marker"], s1["marker"])
        self.assertNotEqual(s0["linestyle"], s1["linestyle"])
        self.assertNotEqual(s0["hatch"], s1["hatch"])

    def test_index_wraps_around(self):
        n = len(MARKER_CYCLE)
        self.assertEqual(get_series_style(0)["marker"], get_series_style(n)["marker"])

    def test_all_cycles_have_8_entries(self):
        self.assertEqual(len(MARKER_CYCLE), 8)
        self.assertEqual(len(HATCH_CYCLE), 8)

    def test_linestyle_cycle_length(self):
        self.assertEqual(len(LINESTYLE_CYCLE), 4)

    def test_returns_dict_with_three_keys(self):
        sty = get_series_style(3)
        self.assertEqual(set(sty.keys()), {"marker", "linestyle", "hatch"})


class TestProfileResolution(unittest.TestCase):
    """Tests for resolve_profile_name and related helpers."""

    def test_default_resolves_to_baseline(self):
        self.assertEqual(resolve_profile_name(None), "baseline")

    def test_alias_premium(self):
        self.assertEqual(resolve_profile_name("premium"), "resistance_premium")

    def test_alias_resistance(self):
        self.assertEqual(resolve_profile_name("resistance"), "resistance_premium")

    def test_unknown_falls_back_to_baseline(self):
        self.assertEqual(resolve_profile_name("nonexistent_profile"), "baseline")

    def test_list_profiles_contains_baseline(self):
        self.assertIn("baseline", list_profiles())

    def test_get_profile_tokens_returns_dict(self):
        tokens, key = get_profile_tokens("baseline")
        self.assertIsInstance(tokens, dict)
        self.assertEqual(key, "baseline")
        self.assertIn("main_marker_size", tokens)

    def test_nature_baseline_resolves_smaller_marker_tokens(self):
        tokens, meta = get_render_style_tokens("nature", "baseline")

        self.assertEqual(meta["target_format"], "nature")
        self.assertEqual(meta["profile"], "baseline")
        self.assertEqual(tokens["figure_width_mm"], 88.0)
        self.assertEqual(tokens["figure_column_widths_mm"], {"single": 88.0, "double": 180.0, "full": 180.0})
        self.assertNotIn("default_colormap", tokens)
        self.assertEqual(tokens["main_marker_size"], 3.2)
        self.assertEqual(tokens["main_marker_edge_width"], 0.6)
        self.assertEqual(tokens["main_line_width"], 1.2)
        self.assertEqual(tokens["facet_marker_size"], 2.4)
        self.assertEqual(tokens["axis_marker_margin_fraction"], 0.06)
        self.assertEqual(tokens["facet_axis_marker_margin_fraction"], 0.16)
        self.assertEqual(tokens["violin_kde_points"], 256)
        self.assertEqual(tokens["violin_kde_bw_method"], "scott")
        self.assertEqual(tokens["violin_width"], 0.52)
        self.assertEqual(tokens["figure_height_mm"], 71.0)
        self.assertLess(tokens["facet_marker_size"], tokens["main_marker_size"])

    def test_science_baseline_resolves_aaas_track_tokens(self):
        tokens, meta = get_render_style_tokens("science", "baseline")

        self.assertEqual(meta["target_format"], "science")
        self.assertEqual(meta["profile"], "baseline")
        self.assertEqual(
            tokens["figure_column_widths_mm"],
            {"single": 57.0, "double": 121.0, "full": 184.0, "triple": 184.0},
        )
        self.assertEqual(tokens["figure_width_mm"], 57.0)
        self.assertEqual(tokens["figure_height_mm"], 45.6)
        self.assertEqual(tokens["main_marker_size"], 3.0)
        self.assertEqual(tokens["facet_marker_size"], 2.2)
        self.assertEqual(tokens["main_marker_edge_width"], 0.5)
        self.assertEqual(tokens["main_line_width"], 0.9)
        self.assertEqual(tokens["timeseries_line_width"], 0.75)
        self.assertEqual(tokens["error_line_width"], 0.7)
        self.assertEqual(tokens["error_cap_size"], 1.8)
        self.assertEqual(tokens["jitter_size"], 10.0)
        self.assertEqual(tokens["jitter_line_width"], 0.5)
        self.assertEqual(tokens["bar_edge_width"], 0.45)
        self.assertEqual(tokens["violin_kde_points"], 192)
        self.assertEqual(tokens["violin_width"], 0.48)
        self.assertEqual(tokens["default_colormap"], "viridis")

    def test_acs_baseline_resolves_distinct_journal_track_tokens(self):
        tokens, meta = get_render_style_tokens("acs", "baseline")

        self.assertEqual(meta["target_format"], "acs")
        self.assertEqual(meta["profile"], "baseline")
        self.assertEqual(
            tokens["figure_column_widths_mm"],
            {"single": 84.67, "double": 177.8, "full": 177.8},
        )
        self.assertEqual(tokens["figure_width_mm"], 84.67)
        self.assertEqual(tokens["figure_height_mm"], 67.736)
        self.assertEqual(tokens["main_marker_size"], 3.4)
        self.assertEqual(tokens["facet_marker_size"], 2.6)
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

    def test_wiley_baseline_resolves_advanced_materials_track_tokens(self):
        tokens, meta = get_render_style_tokens("wiley", "baseline")

        self.assertEqual(meta["target_format"], "wiley")
        self.assertEqual(meta["profile"], "baseline")
        self.assertEqual(
            tokens["figure_column_widths_mm"],
            {"single": 85.0, "double": 178.0, "full": 178.0},
        )
        self.assertEqual(tokens["figure_width_mm"], 85.0)
        self.assertEqual(tokens["figure_height_mm"], 68.0)
        self.assertEqual(tokens["main_marker_size"], 3.5)
        self.assertEqual(tokens["facet_marker_size"], 2.7)
        self.assertEqual(tokens["main_marker_edge_width"], 0.55)
        self.assertEqual(tokens["main_line_width"], 1.0)
        self.assertEqual(tokens["timeseries_line_width"], 0.85)
        self.assertEqual(tokens["error_line_width"], 0.8)
        self.assertEqual(tokens["error_cap_size"], 2.0)
        self.assertEqual(tokens["jitter_size"], 12.5)
        self.assertEqual(tokens["jitter_line_width"], 0.55)
        self.assertEqual(tokens["bar_edge_width"], 0.55)
        self.assertEqual(tokens["violin_kde_points"], 192)
        self.assertEqual(tokens["violin_width"], 0.5)
        self.assertEqual(tokens["default_colormap"], "viridis")

    def test_journal_compliance_tokens_resolve_for_each_track(self):
        expected = {
            "nature": {"min_font_size_pt": 5.0, "min_line_width_pt": 0.25, "max_figure_height_mm": 247.0},
            "science": {"min_font_size_pt": 5.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 234.0},
            "acs": {"min_font_size_pt": 4.5, "min_line_width_pt": 0.5, "max_figure_height_mm": 233.0},
            "wiley": {"min_font_size_pt": 5.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 234.0},
            "cell": {"min_font_size_pt": 6.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 200.0},
            "rsc": {"min_font_size_pt": 7.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 233.0},
            "elsevier": {"min_font_size_pt": 7.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 234.0},
        }

        for target_format, expected_tokens in expected.items():
            with self.subTest(target_format=target_format):
                tokens, meta = get_render_style_tokens(target_format, "baseline")

                self.assertEqual(meta["target_format"], target_format)
                for key, expected_value in expected_tokens.items():
                    self.assertEqual(tokens[key], expected_value)

    def test_journal_compliance_tokens_resolve_for_non_baseline_profile(self):
        baseline_tokens, _baseline_meta = get_render_style_tokens("science", "baseline")
        profile_tokens, profile_meta = get_render_style_tokens("science", "resistance_premium")

        self.assertEqual(profile_meta["target_format"], "science")
        self.assertEqual(profile_meta["profile"], "resistance_premium")
        for key in ("min_font_size_pt", "min_line_width_pt", "max_figure_height_mm"):
            self.assertEqual(profile_tokens[key], baseline_tokens[key])


if __name__ == "__main__":
    unittest.main()
