import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from plotting.axis_break import _draw_break_marks, render_broken_y_axis


class TestBrokenYAxis(unittest.TestCase):
    def _make_data(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0,
                       1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([1.0, 3.0, 5.0, 7.0, 9.0,
                       91.0, 93.0, 95.0, 97.0, 99.0])
        return x, y

    def test_broken_axis_renders_both_ranges(self):
        x, y = self._make_data()
        fig = plt.figure()
        try:
            ax_top, ax_bot = render_broken_y_axis(
                fig,
                [0.1, 0.1, 0.8, 0.8],
                x,
                y,
                (15.0, 85.0),
            )
            top_ymin, top_ymax = ax_top.get_ylim()
            bot_ymin, bot_ymax = ax_bot.get_ylim()
            self.assertGreater(top_ymax, 85.0)
            self.assertLess(bot_ymin, 15.0)
            self.assertGreater(bot_ymax, 9.0)
        finally:
            plt.close(fig)

    def test_broken_axis_no_data_distortion(self):
        x, y = self._make_data()
        fig = plt.figure()
        try:
            ax_top, ax_bot = render_broken_y_axis(
                fig,
                [0.1, 0.1, 0.8, 0.8],
                x,
                y,
                (15.0, 85.0),
            )
            for ax in (ax_top, ax_bot):
                for coll in ax.collections:
                    if hasattr(coll, "get_offsets"):
                        offsets = coll.get_offsets()
                        if len(offsets):
                            np.testing.assert_array_equal(offsets[:, 0], x)
        finally:
            plt.close(fig)

    def test_break_marks_drawn(self):
        fig = plt.figure()
        try:
            ax_top = fig.add_axes([0.1, 0.55, 0.8, 0.35])
            ax_bot = fig.add_axes([0.1, 0.1, 0.8, 0.35])
            lines_before_top = len(ax_top.lines)
            lines_before_bot = len(ax_bot.lines)
            _draw_break_marks(ax_top, ax_bot, style="diagonal")
            self.assertEqual(len(ax_top.lines) - lines_before_top, 2)
            self.assertEqual(len(ax_bot.lines) - lines_before_bot, 2)
        finally:
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
