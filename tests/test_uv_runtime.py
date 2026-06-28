import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

HUB_ROOT = Path(__file__).resolve().parent.parent
UV_RUNTIME_PATH = HUB_ROOT / "hub_core" / "uv_runtime.py"


def _load_uv_runtime():
    spec = importlib.util.spec_from_file_location("_figops_uv_runtime_test", UV_RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load uv_runtime: {UV_RUNTIME_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uv_runtime = _load_uv_runtime()
build_uv_environment = uv_runtime.build_uv_environment
resolve_uv_project_environment = uv_runtime.resolve_uv_project_environment
run_uv = uv_runtime.run_uv


class UvRuntimeTest(unittest.TestCase):
    def test_uv_project_environment_is_outside_hub_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = (Path(tmpdir) / "runtime").resolve()

            env_path = Path(resolve_uv_project_environment(HUB_ROOT, runtime_root))

            self.assertTrue(str(env_path).startswith(str(runtime_root)))
            self.assertNotEqual(env_path, HUB_ROOT / ".venv")
            self.assertNotIn(str(HUB_ROOT), str(env_path))
            self.assertEqual(env_path.name, "figops")

    def test_build_uv_environment_pins_project_env_and_cache(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = (Path(tmpdir) / "runtime").resolve()
            base_env = {"PATH": os.environ.get("PATH", ""), "UV_PROJECT_ENVIRONMENT": str(HUB_ROOT / ".venv")}

            env = build_uv_environment(base_env, HUB_ROOT, runtime_root)

            self.assertEqual(env["PATH"], base_env["PATH"])
            self.assertEqual(env["RESEARCH_HUB_RUNTIME_ROOT"], str(runtime_root))
            self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(runtime_root / "uv_envs" / "figops"))
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
            self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(runtime_root / "uv_envs" / "figops"))
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

    def test_run_uv_missing_executable_fails_with_actionable_message(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = (Path(tmpdir) / "runtime").resolve()
            env = build_uv_environment({"PATH": ""}, HUB_ROOT, runtime_root)
            stderr = StringIO()
            with (
                patch.object(uv_runtime, "build_uv_environment", return_value=env),
                patch.object(uv_runtime.shutil, "which", return_value=None),
                patch.object(uv_runtime.subprocess, "call") as call,
                redirect_stderr(stderr),
            ):
                result = run_uv(["run", "python", "-V"], cwd=HUB_ROOT)

        self.assertEqual(result, 127)
        self.assertIn("uv", stderr.getvalue().lower())
        self.assertIn("PATH", stderr.getvalue())
        call.assert_not_called()

    def test_run_uv_returns_subprocess_exit_code_when_uv_exists(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = (Path(tmpdir) / "runtime").resolve()
            env = build_uv_environment({"PATH": os.environ.get("PATH", "")}, HUB_ROOT, runtime_root)
            with (
                patch.object(uv_runtime, "build_uv_environment", return_value=env),
                patch.object(uv_runtime.shutil, "which", return_value="uv"),
                patch.object(uv_runtime.subprocess, "call", return_value=3) as call,
            ):
                result = run_uv(["run", "python", "-V"], cwd=HUB_ROOT)

        self.assertEqual(result, 3)
        call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
