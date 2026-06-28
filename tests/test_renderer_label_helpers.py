import unittest

from plotting.bridge_renderer import (
    _annotate_points,
    _display_label,
    _normalized_point_label_options_dict,
    _point_label_candidates,
)
from plotting.renderers import labels


class RendererLabelHelperTest(unittest.TestCase):
    def test_bridge_renderer_keeps_label_helper_compatibility_aliases(self):
        self.assertIs(_annotate_points, labels.annotate_points)
        self.assertIs(_display_label, labels.display_label)
        self.assertIs(_normalized_point_label_options_dict, labels.normalized_point_label_options_dict)
        self.assertIs(_point_label_candidates, labels.point_label_candidates)

    def test_label_helper_normalizes_static_offset(self):
        options = labels.normalized_point_label_options_dict({"offset": {"dx": "3", "dy": 7}})

        self.assertEqual(options["offset"], (3.0, 7.0))

    def test_label_helper_rejects_non_finite_priority(self):
        with self.assertRaisesRegex(ValueError, "must be finite"):
            labels.point_label_candidates(
                [0.0],
                [1.0],
                ["bad"],
                options={"priority_column": "priority"},
                points=[{"raw": {"priority": "nan"}}],
            )


if __name__ == "__main__":
    unittest.main()
