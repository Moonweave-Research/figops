import unittest
from types import SimpleNamespace

from plotting.bridge_renderer import (
    _apply_tick_style,
    _normalized_axis_scale,
    _normalized_tick_style,
    _validate_axis_scales,
)
from plotting.renderers import axes


class RendererAxisHelperTest(unittest.TestCase):
    def test_bridge_renderer_keeps_axis_helper_compatibility_aliases(self):
        self.assertIs(_apply_tick_style, axes.apply_tick_style)
        self.assertIs(_normalized_axis_scale, axes.normalized_axis_scale)
        self.assertIs(_normalized_tick_style, axes.normalized_tick_style)
        self.assertIs(_validate_axis_scales, axes.validate_axis_scales)

    def test_axis_helper_rejects_non_positive_log_values(self):
        spec = SimpleNamespace(x_scale="log", y_scale="linear")

        with self.assertRaisesRegex(ValueError, "requires finite numeric x values > 0"):
            axes.validate_axis_scales([{"x": 0.0, "y": 1.0}], spec)

    def test_tick_style_helper_normalizes_rotation_and_format(self):
        spec = SimpleNamespace(tick_style={"rotation": "45", "format": "compact", "max_label_chars": "8"})

        self.assertEqual(
            axes.normalized_tick_style(spec),
            {"rotation": 45.0, "format": "compact", "max_label_chars": 8},
        )


if __name__ == "__main__":
    unittest.main()
