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
LAUNCHER_PATH = HUB_ROOT / "graphhub_mcp_launcher.py"


def _load_uv_runtime():
    spec = importlib.util.spec_from_file_location("_figops_uv_runtime_test", UV_RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load uv_runtime: {UV_RUNTIME_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_launcher():
    spec = importlib.util.spec_from_file_location("_figops_graphhub_launcher_test", LAUNCHER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load launcher: {LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uv_runtime = _load_uv_runtime()
launcher = _load_launcher()
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
        self.assertIn("RESEARCH_HUB_RUNTIME_ROOT=", completed.stdout)
        self.assertIn("UV_PROJECT_ENVIRONMENT=", completed.stdout)
        self.assertIn("UV_CACHE_DIR=", completed.stdout)

    def test_hub_uv_help_uses_current_python_executable_name(self):
        completed = subprocess.run(
            [sys.executable, "hub_uv.py", "--help"],
            cwd=HUB_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(f"Usage: {Path(sys.executable).name} hub_uv.py", completed.stdout)
        self.assertIn(f"Example: {Path(sys.executable).name} hub_uv.py run python", completed.stdout)

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

    def test_graphhub_launcher_uses_figops_uv_environment_name(self):
        runtime_root = Path("runtime-root")

        venv_python = launcher._venv_python(runtime_root)

        self.assertEqual(venv_python.parent.parent.name, "figops")
        if os.name == "nt":
            self.assertEqual(venv_python.name, "python.exe")
            self.assertEqual(venv_python.parent.name, "Scripts")
        else:
            self.assertEqual(venv_python.name, "python")
            self.assertEqual(venv_python.parent.name, "bin")

    def test_graphhub_launcher_fallback_execs_hub_uv_with_current_python(self):
        exec_calls = []

        def fake_execv(executable, args):
            exec_calls.append((executable, args))
            raise SystemExit(0)

        with tempfile.TemporaryDirectory(prefix="graph_hub_launcher_") as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"
            with (
                patch.object(launcher, "_runtime_root", return_value=runtime_root),
                patch.object(launcher.os, "execv", side_effect=fake_execv),
                patch.object(launcher.sys, "argv", ["graphhub_mcp_launcher.py", "--smoke"]),
            ):
                with self.assertRaises(SystemExit):
                    launcher.main()

        self.assertEqual(exec_calls[0][0], sys.executable)
        self.assertEqual(exec_calls[0][1][0], sys.executable)
        self.assertIn("hub_uv.py", exec_calls[0][1][1])
        self.assertEqual(exec_calls[0][1][2:4], ["run", "python"])


if __name__ == "__main__":
    unittest.main()
