import unittest
from types import SimpleNamespace

from plotting.bridge_renderer import (
    _apply_legend,
    _avoid_smart_legend_data_collision,
    _find_best_legend_location,
    _normalized_legend_options,
    _resolved_legend_layout,
)
from plotting.renderers import legend


class RendererLegendHelperTest(unittest.TestCase):
    def test_bridge_renderer_keeps_legend_helper_compatibility_aliases(self):
        self.assertIs(_apply_legend, legend.apply_legend)
        self.assertIs(_avoid_smart_legend_data_collision, legend.avoid_smart_legend_data_collision)
        self.assertIs(_find_best_legend_location, legend.find_best_legend_location)
        self.assertIs(_normalized_legend_options, legend.normalized_legend_options)
        self.assertIs(_resolved_legend_layout, legend.resolved_legend_layout)

    def test_legend_helper_normalizes_order_and_ncol(self):
        spec = SimpleNamespace(legend_options={"title": "Group", "order": ["B", "A"], "ncol": "2"})

        self.assertEqual(
            legend.normalized_legend_options(spec),
            {"title": "Group", "order": ("B", "A"), "ncol": 2},
        )

    def test_legend_helper_rejects_duplicate_order_labels(self):
        spec = SimpleNamespace(legend_options={"order": ["A", "A"]})

        with self.assertRaisesRegex(ValueError, "must not contain duplicate"):
            legend.normalized_legend_options(spec)


if __name__ == "__main__":
    unittest.main()
