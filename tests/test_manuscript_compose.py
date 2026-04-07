import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")

from plotting.bridge_renderer import (  # noqa: E402
    BridgeFigureSpec,
    MultiPanelSpec,
    render_multipanel_figure,
)

_MM_TOLERANCE = 1.0 / 25.4  # 1 mm in figure-fraction units at typical sizes


def _make_csv(tmpdir: Path, name: str) -> Path:
    p = tmpdir / name
    p.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    return p


def _standard_panel(csv_path: str, output_path: str, title: str = "") -> BridgeFigureSpec:
    return BridgeFigureSpec(
        csv_path=csv_path,
        output_path=output_path,
        plot_type="line",
        x_column="x",
        y_column="y",
        title=title,
        legend_layout="standard",
    )


class TestManuscriptCompose(unittest.TestCase):

    def test_manuscript_2x2_panel_positions(self):
        with tempfile.TemporaryDirectory(prefix="ms_2x2_") as tmpdir:
            d = Path(tmpdir)
            panels = tuple(
                _standard_panel(str(_make_csv(d, f"p{i}.csv")), str(d / f"p{i}.png"), title=f"P{i}")
                for i in range(4)
            )
            spec = MultiPanelSpec(
                panels=panels,
                output_path=str(d / "out.png"),
                rows=2,
                cols=2,
                column_width="double",
                panel_height_mm=65.0,
                gutter_h_mm=5.0,
                gutter_v_mm=5.0,
                compose_mode="manuscript",
            )

            with patch("plotting.bridge_renderer.save_journal_fig") as mock_save:
                render_multipanel_figure(spec)

            fig = mock_save.call_args.args[0]
            fig_w_mm, fig_h_mm = (v * 25.4 for v in fig.get_size_inches())

            # fig dimensions: 183 x (65*2 + 5) = 183 x 135
            self.assertAlmostEqual(fig_w_mm, 183.0, places=1)
            self.assertAlmostEqual(fig_h_mm, 135.0, places=1)

            axes = [ax for ax in fig.axes if ax.get_visible()]
            self.assertEqual(len(axes), 4)

            # cell_w = (183 - 5) / 2 = 89, standard box = 70x55mm
            # margins: left=14, right=5, bottom=12, top=8
            # left_extra = 19 * 14/19 = 14, bottom_extra = 10 * 12/20 = 6
            # col=1 cell_left = 1*(89+5) = 94, ax_left = 94+14 = 108
            # row=0 cell_bottom = 135 - 1*65 - 0*5 = 70, ax_bottom = 70+6 = 76
            # row=1 cell_bottom = 135 - 2*65 - 1*5 = 0, ax_bottom = 0+6 = 6
            expected_positions_mm = [
                # (ax_left_mm, ax_bottom_mm, ax_width_mm, ax_height_mm) for each panel
                (14.0,   76.0, 70.0, 55.0),   # row=0, col=0
                (108.0,  76.0, 70.0, 55.0),   # row=0, col=1
                (14.0,    6.0, 70.0, 55.0),   # row=1, col=0
                (108.0,   6.0, 70.0, 55.0),   # row=1, col=1
            ]

            for ax, (exp_left_mm, exp_bottom_mm, exp_w_mm, exp_h_mm) in zip(
                axes, expected_positions_mm
            ):
                pos = ax.get_position()
                got_left_mm = pos.x0 * fig_w_mm
                got_bottom_mm = pos.y0 * fig_h_mm
                got_w_mm = pos.width * fig_w_mm
                got_h_mm = pos.height * fig_h_mm
                self.assertAlmostEqual(got_left_mm, exp_left_mm, delta=1.0)
                self.assertAlmostEqual(got_bottom_mm, exp_bottom_mm, delta=1.0)
                self.assertAlmostEqual(got_w_mm, exp_w_mm, delta=1.0)
                self.assertAlmostEqual(got_h_mm, exp_h_mm, delta=1.0)

    def test_manuscript_spine_alignment(self):
        with tempfile.TemporaryDirectory(prefix="ms_spine_") as tmpdir:
            d = Path(tmpdir)
            panels = tuple(
                _standard_panel(str(_make_csv(d, f"s{i}.csv")), str(d / f"s{i}.png"))
                for i in range(4)
            )
            spec = MultiPanelSpec(
                panels=panels,
                output_path=str(d / "out.png"),
                rows=2,
                cols=2,
                column_width="double",
                panel_height_mm=65.0,
                gutter_h_mm=5.0,
                gutter_v_mm=5.0,
                compose_mode="manuscript",
            )

            with patch("plotting.bridge_renderer.save_journal_fig") as mock_save:
                render_multipanel_figure(spec)

            fig = mock_save.call_args.args[0]
            axes = [ax for ax in fig.axes if ax.get_visible()]
            self.assertEqual(len(axes), 4)

            fig_w_mm = fig.get_size_inches()[0] * 25.4

            # col-0 panels: index 0 and 2 (top-left, bottom-left)
            col0_lefts = [axes[i].get_position().x0 * fig_w_mm for i in (0, 2)]
            self.assertAlmostEqual(col0_lefts[0], col0_lefts[1], delta=1.0)

            # col-1 panels: index 1 and 3 (top-right, bottom-right)
            col1_lefts = [axes[i].get_position().x0 * fig_w_mm for i in (1, 3)]
            self.assertAlmostEqual(col1_lefts[0], col1_lefts[1], delta=1.0)

    def test_manuscript_empty_cells(self):
        with tempfile.TemporaryDirectory(prefix="ms_empty_") as tmpdir:
            d = Path(tmpdir)
            panels = tuple(
                _standard_panel(str(_make_csv(d, f"e{i}.csv")), str(d / f"e{i}.png"))
                for i in range(3)
            )
            spec = MultiPanelSpec(
                panels=panels,
                output_path=str(d / "out.png"),
                rows=2,
                cols=2,
                column_width="double",
                panel_height_mm=65.0,
                gutter_h_mm=5.0,
                gutter_v_mm=5.0,
                compose_mode="manuscript",
            )

            with patch("plotting.bridge_renderer.save_journal_fig") as mock_save:
                render_multipanel_figure(spec)

            fig = mock_save.call_args.args[0]
            axes = [ax for ax in fig.axes if ax.get_visible()]
            self.assertEqual(len(axes), 3)


if __name__ == "__main__":
    unittest.main()
