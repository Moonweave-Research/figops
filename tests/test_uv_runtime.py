import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from hub_core.uv_runtime import build_uv_environment, resolve_uv_project_environment

HUB_ROOT = Path(__file__).resolve().parent.parent


class UvRuntimeTest(unittest.TestCase):
    def test_uv_project_environment_is_outside_hub_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = (Path(tmpdir) / "runtime").resolve()

            env_path = Path(resolve_uv_project_environment(HUB_ROOT, runtime_root))

            self.assertTrue(str(env_path).startswith(str(runtime_root)))
            self.assertNotEqual(env_path, HUB_ROOT / ".venv")
            self.assertNotIn(str(HUB_ROOT), str(env_path))
            self.assertEqual(env_path.name, "graph-making-hub")

    def test_build_uv_environment_pins_project_env_and_cache(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = (Path(tmpdir) / "runtime").resolve()
            base_env = {"PATH": os.environ.get("PATH", ""), "UV_PROJECT_ENVIRONMENT": str(HUB_ROOT / ".venv")}

            env = build_uv_environment(base_env, HUB_ROOT, runtime_root)

            self.assertEqual(env["PATH"], base_env["PATH"])
            self.assertEqual(env["RESEARCH_HUB_RUNTIME_ROOT"], str(runtime_root))
            self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(runtime_root / "uv_envs" / "graph-making-hub"))
            self.assertEqual(env["UV_CACHE_DIR"], str(runtime_root / "uv_cache"))

    def test_build_uv_environment_respects_base_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = (Path(tmpdir) / "from_base_env").resolve()
            base_env = {
                "PATH": os.environ.get("PATH", ""),
                "RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root),
            }

            env = build_uv_environment(base_env, HUB_ROOT)

            self.assertEqual(env["RESEARCH_HUB_RUNTIME_ROOT"], str(runtime_root))
            self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(runtime_root / "uv_envs" / "graph-making-hub"))
            self.assertEqual(env["UV_CACHE_DIR"], str(runtime_root / "uv_cache"))

    def test_hub_uv_print_env_does_not_import_yaml(self):
        script = textwrap.dedent(
            f"""
            import builtins
            import runpy
            import sys

            original_import = builtins.__import__

            def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "yaml":
                    raise ModuleNotFoundError("No module named 'yaml'")
                return original_import(name, globals, locals, fromlist, level)

            builtins.__import__ = guarded_import
            sys.argv = [{str(HUB_ROOT / "hub_uv.py")!r}, "--print-env"]
            runpy.run_path({str(HUB_ROOT / "hub_uv.py")!r}, run_name="__main__")
            """
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=HUB_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("UV_PROJECT_ENVIRONMENT=", completed.stdout)


if __name__ == "__main__":
    unittest.main()
