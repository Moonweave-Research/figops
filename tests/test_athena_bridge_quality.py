"""
Tests for AthenaBridge quality-aware visual feedback.

Covers: _read_quality_sidecar, _apply_quality_overlay
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib  # noqa: I001

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: I001, E402
from PIL import Image  # noqa: E402

from hub_core.athena_bridge import AthenaBridge  # noqa: E402
from hub_core.runtime_paths import resolve_diagnostics_dir  # noqa: E402
from themes.journal_theme import apply_publication_layout, mm_to_inch  # noqa: E402


class TestReadQualitySidecar(unittest.TestCase):
    """Tests for AthenaBridge._read_quality_sidecar (static method)."""

    def test_reads_valid_sidecar(self, tmp_path=None):
        """Legacy project-local quality diagnostics remain readable."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            diag = Path(tmpdir) / "results" / "diagnostics"
            diag.mkdir(parents=True)
            payload = {"quality_passed": False, "cv_warnings": [{"column": "x", "cv": 0.5}]}
            (diag / "quality_metrics.json").write_text(json.dumps(payload), encoding="utf-8")

            # output_path is inside the project tree
            output_path = str(Path(tmpdir) / "results" / "figures" / "fig.png")
            result = AthenaBridge._read_quality_sidecar(output_path)
            self.assertIsNotNone(result)
            self.assertFalse(result["quality_passed"])

    def test_prefers_external_runtime_sidecar_without_project_local_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            runtime = root / "runtime"
            output_path = project / "results" / "figures" / "fig.png"
            output_path.parent.mkdir(parents=True)
            payload = {"quality_passed": False, "cv_warnings": [{"column": "x", "cv": 0.5}]}

            with patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime)}, clear=False):
                sidecar = Path(resolve_diagnostics_dir(project)) / "data_contract" / "quality_metrics.json"
                sidecar.parent.mkdir(parents=True)
                sidecar.write_text(json.dumps(payload), encoding="utf-8")
                result = AthenaBridge._read_quality_sidecar(str(output_path))

            self.assertEqual(result, payload)
            self.assertTrue(sidecar.is_relative_to(runtime))
            self.assertFalse((project / "results" / "diagnostics" / "quality_metrics.json").exists())

    def test_missing_sidecar_returns_none(self):
        """No sidecar file should return None."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "results" / "figures" / "fig.png")
            result = AthenaBridge._read_quality_sidecar(output_path)
            self.assertIsNone(result)

    def test_malformed_json_returns_none(self):
        """Corrupt JSON should return None without raising."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            diag = Path(tmpdir) / "results" / "diagnostics"
            diag.mkdir(parents=True)
            (diag / "quality_metrics.json").write_text("{bad!!!", encoding="utf-8")

            output_path = str(Path(tmpdir) / "results" / "figures" / "fig.png")
            result = AthenaBridge._read_quality_sidecar(output_path)
            self.assertIsNone(result)


class TestApplyQualityOverlay(unittest.TestCase):
    """Tests for AthenaBridge._apply_quality_overlay (static method)."""

    def test_overlay_adds_patches_and_text(self):
        """Overlay should add blur patches and warning text to the figure."""
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])

        quality_info = {
            "quality_passed": False,
            "cv_warnings": [{"column": "thickness", "cv": 0.35}],
            "cv_threshold": 0.1,
        }

        patches_before = len(fig.patches)
        texts_before = len(fig.texts)

        AthenaBridge._apply_quality_overlay(fig, quality_info)

        # Should have added at least one blur patch
        self.assertGreater(len(fig.patches), patches_before)
        # Should have added at least watermark + detail text
        self.assertGreaterEqual(len(fig.texts) - texts_before, 2)

        plt.close(fig)

    def test_overlay_with_many_warnings_truncates(self):
        """More than 4 warnings should show '+N more' in detail text."""
        fig, ax = plt.subplots()
        ax.plot([1, 2], [1, 2])

        warnings = [{"column": f"col_{i}", "cv": 0.5 + i * 0.1} for i in range(6)]
        quality_info = {"quality_passed": False, "cv_warnings": warnings, "cv_threshold": 0.1}

        AthenaBridge._apply_quality_overlay(fig, quality_info)

        detail_texts = [t for t in fig.texts if "+2 more" in t.get_text()]
        self.assertEqual(len(detail_texts), 1)

        plt.close(fig)

    def test_overlay_with_empty_warnings(self):
        """Empty warnings list should still add watermark without crashing."""
        fig, ax = plt.subplots()
        ax.plot([1, 2], [1, 2])

        quality_info = {"quality_passed": False, "cv_warnings": [], "cv_threshold": 0.1}

        AthenaBridge._apply_quality_overlay(fig, quality_info)

        watermarks = [t for t in fig.texts if "QUALITY WARNING" in t.get_text()]
        self.assertEqual(len(watermarks), 1)

        plt.close(fig)


class TestAthenaBridgeRenderSave(unittest.TestCase):
    """Regression tests for AthenaBridge render/save path."""

    def test_render_preserves_layout_locked_canvas_size(self):
        bridge = AthenaBridge()
        original_engine = bridge._engine

        fig, ax = plt.subplots(figsize=(mm_to_inch(89.0), mm_to_inch(75.0)))
        apply_publication_layout("standard", fig=fig, target_format="nature")

        try:
            bridge._engine = {
                "build_device_figure": lambda **kwargs: (fig, ax, {}),
            }

            with tempfile.TemporaryDirectory(prefix="athena_bridge_render_") as tmpdir:
                root = Path(tmpdir)
                output_path = root / "project" / "results" / "figures" / "fig.png"
                runtime_root = root / "runtime"
                with (
                    patch.dict(
                        os.environ,
                        {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)},
                        clear=False,
                    ),
                    patch.object(bridge, "load_engine", return_value=True),
                ):
                    ok = bridge.render(
                        {"layers": [], "target_format": "nature", "dpi": 600},
                        str(output_path),
                    )

                self.assertTrue(ok)
                self.assertTrue(output_path.exists())
                self.assertFalse(output_path.with_suffix(".manifest.json").exists())
                manifests = list(runtime_root.rglob("*.manifest.json"))
                self.assertEqual(len(manifests), 1)
                self.assertTrue(manifests[0].is_relative_to(runtime_root))
                with Image.open(output_path) as saved:
                    self.assertEqual(saved.size, (2102, 1771))
        finally:
            bridge._engine = original_engine
            plt.close(fig)

    def test_manifest_failure_never_leaves_a_durable_output(self):
        bridge = AthenaBridge()
        original_engine = bridge._engine
        fig, ax = plt.subplots(figsize=(2, 1))
        try:
            bridge._engine = {"build_device_figure": lambda **kwargs: (fig, ax, {})}
            with tempfile.TemporaryDirectory(prefix="athena_bridge_failure_") as tmpdir:
                root = Path(tmpdir)
                output_path = root / "project" / "results" / "figures" / "fig.png"
                runtime_root = root / "runtime"
                with (
                    patch.dict(
                        os.environ,
                        {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)},
                        clear=False,
                    ),
                    patch.object(bridge, "load_engine", return_value=True),
                    patch.object(bridge, "_write_manifest", side_effect=OSError("manifest failed")),
                ):
                    ok = bridge.render(
                        {"layers": [], "target_format": "nature", "dpi": 300},
                        str(output_path),
                    )

                self.assertFalse(ok)
                self.assertFalse(output_path.exists())
                self.assertTrue(list(runtime_root.rglob("*.png")))
        finally:
            bridge._engine = original_engine
            plt.close(fig)

    def test_promotion_failure_never_leaves_a_durable_output(self):
        bridge = AthenaBridge()
        original_engine = bridge._engine
        fig, ax = plt.subplots(figsize=(2, 1))
        try:
            bridge._engine = {"build_device_figure": lambda **kwargs: (fig, ax, {})}
            with tempfile.TemporaryDirectory(prefix="athena_bridge_promotion_failure_") as tmpdir:
                root = Path(tmpdir)
                output_path = root / "project" / "results" / "figures" / "fig.png"
                runtime_root = root / "runtime"
                with (
                    patch.dict(
                        os.environ,
                        {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)},
                        clear=False,
                    ),
                    patch.object(bridge, "load_engine", return_value=True),
                    patch(
                        "hub_core.athena_bridge.promote_runtime_artifact",
                        side_effect=OSError("promotion failed"),
                    ),
                ):
                    ok = bridge.render(
                        {"layers": [], "target_format": "nature", "dpi": 300},
                        str(output_path),
                    )

                self.assertFalse(ok)
                self.assertFalse(output_path.exists())
                self.assertTrue(list(runtime_root.rglob("*.png")))
        finally:
            bridge._engine = original_engine
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
