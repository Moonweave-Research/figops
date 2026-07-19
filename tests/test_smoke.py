import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hub_core.cache_manager import BUILD_STATE_SCHEMA_VERSION
from hub_core.path_identity import canonical_path
from hub_core.runtime_paths import resolve_build_state_path

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
    @unittest.skipUnless(
        _r_packages_available(),
        "R runtime + readr package required for full scaffold analysis step",
    )
    def test_scaffold_all_and_cache(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_smoke_", dir=HUB_ROOT.parent) as tmpdir:
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
                    "--verbose",
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

            # Build state is disposable runtime state. Resolve its location
            # through the same runtime API and root policy used by the child
            # orchestrator, rather than reconstructing its cache layout here.
            runtime_home = tmp_path / "runtime_home"
            with mock.patch.dict(
                os.environ,
                {
                    "RESEARCH_HUB_RUNTIME_HOME": str(runtime_home),
                    "RESEARCH_HUB_RUNTIME_ROOT": str(runtime_home),
                },
                clear=False,
            ):
                state_path = Path(resolve_build_state_path(project_dir))
            self.assertTrue(state_path.exists())
            # Canonical identities deliberately make a macOS /var ->
            # /private/var system alias an internal runtime location without
            # accepting any user-controlled symlink as an alias exception.
            self.assertTrue(
                canonical_path(state_path, strict=True).is_relative_to(canonical_path(runtime_home, strict=True))
            )
            self.assertFalse(list(project_dir.rglob(".build_state.json")))
            state_bytes = state_path.read_bytes()
            state = json.loads(state_bytes)
            self.assertEqual(state["version"], BUILD_STATE_SCHEMA_VERSION)
            self.assertTrue(state["config_hash"])
            self.assertTrue(state["analysis"])
            self.assertTrue(state["figures"])
            self.assertTrue(state["diagrams"])

            rerun_result = self._run(
                [
                    sys.executable,
                    str(ORCHESTRATOR),
                    "--project",
                    str(project_dir),
                    "--step",
                    "all",
                    "--strict-lock",
                    "--verbose",
                ],
                tmp_path,
            )
            self.assertEqual(rerun_result.returncode, 0, rerun_result.stdout)
            self.assertIn("[SKIP] analysis 1", rerun_result.stdout)
            self.assertIn("[SKIP] plot Fig1", rerun_result.stdout)
            self.assertIn("[SKIP] diagram DeviceCrossSection", rerun_result.stdout)
            self.assertTrue(state_path.exists())
            self.assertEqual(state_path.read_bytes(), state_bytes)
            self.assertFalse(list(project_dir.rglob(".build_state.json")))

    def _run(self, cmd, tmp_path):
        env = os.environ.copy()
        runtime_home = tmp_path / "runtime_home"
        env.pop("PROJECT_ROOT", None)
        env["RESEARCH_HUB_PATH"] = str(HUB_ROOT)
        env["RESEARCH_HUB_RUNTIME_HOME"] = str(runtime_home)
        env["RESEARCH_HUB_RUNTIME_ROOT"] = str(runtime_home)
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

    def test_run_neutralizes_ambient_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_smoke_env_") as tmpdir:
            tmp_path = Path(tmpdir)
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "PROJECT_ROOT": "/ambient/active/project",
                        "RESEARCH_HUB_PATH": "/ambient/research/hub",
                        "RESEARCH_HUB_RUNTIME_ROOT": "/ambient/runtime/root",
                        "RESEARCH_HUB_RUNTIME_HOME": "/ambient/runtime/home",
                    },
                    clear=False,
                ),
                mock.patch("subprocess.run") as run_mock,
            ):
                run_mock.return_value = subprocess.CompletedProcess(["demo"], 0, "", "")

                self._run([sys.executable, "-c", "print('demo')"], tmp_path)

            passed_env = run_mock.call_args.kwargs["env"]
            expected_runtime = str(tmp_path / "runtime_home")
            self.assertNotIn("PROJECT_ROOT", passed_env)
            self.assertEqual(passed_env["RESEARCH_HUB_PATH"], str(HUB_ROOT))
            self.assertEqual(passed_env["RESEARCH_HUB_RUNTIME_HOME"], expected_runtime)
            self.assertEqual(passed_env["RESEARCH_HUB_RUNTIME_ROOT"], expected_runtime)


if __name__ == "__main__":
    unittest.main()
