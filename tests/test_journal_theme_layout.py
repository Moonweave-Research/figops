import tempfile
import unittest
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from hub_core.scaffold import DEFAULT_DIAGRAM_PY, DEFAULT_PLOT_PY
from hub_core.geometry_diagnostics import diagnose_figure_geometry
from themes.journal_theme import TIFF_AUTO_PRESETS, apply_publication_layout, mm_to_inch, panel_label, save_journal_fig


def _axes_box_mm(fig, ax):
    fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())
    pos = ax.get_position()
    return fig_w_mm * pos.width, fig_h_mm * pos.height


class JournalThemeLayoutTest(unittest.TestCase):
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
                c for c in diagnose_figure_geometry(fig, [ax], layout_locked=False)["checks"] if c["name"] == "artist_overlaps"
            )
            self.assertTrue(check["passed"])
        finally:
            plt.close(fig)

    def test_save_journal_fig_auto_declutter_does_not_move_unrelated_repeated_label(self):
        fig, ax = plt.subplots()
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

    def test_tiff_companion_generated_for_nature_surfur(self):
        self.assertIn("nature_surfur", TIFF_AUTO_PRESETS)
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        try:
            with tempfile.TemporaryDirectory(prefix="journal_tiff_surfur_") as tmpdir:
                png_path = Path(tmpdir) / "figure.png"
                save_journal_fig(fig, png_path, preset="nature_surfur", dpi=150)

                tiff_path = png_path.with_suffix(".tiff")
                self.assertTrue(tiff_path.exists(), "TIFF companion not created for nature_surfur preset")
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
