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
        self.assertEqual(tokens["main_marker_size"], 3.2)
        self.assertEqual(tokens["facet_marker_size"], 2.4)
        self.assertEqual(tokens["violin_kde_points"], 256)
        self.assertEqual(tokens["violin_kde_bw_method"], "scott")
        self.assertEqual(tokens["violin_width"], 0.52)
        self.assertLess(tokens["facet_marker_size"], tokens["main_marker_size"])

    def test_science_baseline_keeps_profile_marker_size(self):
        tokens, meta = get_render_style_tokens("science", "baseline")

        self.assertEqual(meta["target_format"], "science")
        self.assertEqual(meta["profile"], "baseline")
        self.assertEqual(tokens["main_marker_size"], 5.0)
        self.assertEqual(tokens["violin_kde_points"], 100)


if __name__ == "__main__":
    unittest.main()
