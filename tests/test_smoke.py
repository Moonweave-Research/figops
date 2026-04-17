import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

HUB_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = HUB_ROOT / "orchestrator.py"


def _r_packages_available() -> bool:
    """Check whether R + readr + required deps are installed (scaffold analysis needs them)."""
    rscript = shutil.which("Rscript")
    if rscript is None:
        return False
    try:
        result = subprocess.run(
            [rscript, "-e", "suppressPackageStartupMessages(library(readr))"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


class HubSmokeTest(unittest.TestCase):
    @pytest.mark.skipif(
        not _r_packages_available(),
        reason="R runtime + readr package required for full scaffold analysis step",
    )
    def test_scaffold_all_and_cache(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_smoke_") as tmpdir:
            tmp_path = Path(tmpdir)
            project_dir = tmp_path / "smoke_project"

            init_result = self._run(
                [
                    sys.executable,
                    str(ORCHESTRATOR),
                    "--init",
                    "--project",
                    str(project_dir),
                ],
                tmp_path,
            )
            self.assertEqual(init_result.returncode, 0, init_result.stdout)
            self.assertTrue((project_dir / "project_config.yaml").exists())

            full_result = self._run(
                [
                    sys.executable,
                    str(ORCHESTRATOR),
                    "--project",
                    str(project_dir),
                    "--step",
                    "all",
                    "--strict-lock",
                ],
                tmp_path,
            )
            self.assertEqual(full_result.returncode, 0, full_result.stdout)
            self.assertIn("[Data Contract Step]", full_result.stdout)
            self.assertIn("[Plotting Step]", full_result.stdout)
            self.assertIn("[Diagram Step]", full_result.stdout)
            self.assertIn("Output verified", full_result.stdout)
            self.assertTrue((project_dir / "results" / "figures" / "Fig1.png").exists())
            self.assertTrue((project_dir / "results" / "figures" / "device_cross_section.svg").exists())
            self.assertTrue((project_dir / ".build_state.json").exists())

            rerun_result = self._run(
                [
                    sys.executable,
                    str(ORCHESTRATOR),
                    "--project",
                    str(project_dir),
                    "--step",
                    "all",
                    "--strict-lock",
                ],
                tmp_path,
            )
            self.assertEqual(rerun_result.returncode, 0, rerun_result.stdout)
            self.assertIn("[SKIP] analysis 1", rerun_result.stdout)
            self.assertIn("[SKIP] plot Fig1", rerun_result.stdout)
            self.assertIn("[SKIP] diagram DeviceCrossSection", rerun_result.stdout)

    def _run(self, cmd, tmp_path):
        env = os.environ.copy()
        runtime_home = tmp_path / "runtime_home"
        dvc_home = tmp_path / "dvc_home"
        env["RESEARCH_HUB_RUNTIME_HOME"] = str(runtime_home)
        env["RESEARCH_HUB_DVC_HOME"] = str(dvc_home)
        env["PYTHONUNBUFFERED"] = "1"
        return subprocess.run(
            cmd,
            cwd=HUB_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
