"""Unit tests for _build_r_cmd and run_sweep in hub_core.process_runner."""

import csv
import os
import shutil
import sys
import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

import hub_core.process_runner as pr
from hub_core.process_runner import _build_r_cmd, run_analysis, run_comparison, run_plots, run_sweep
from hub_core.process_runner_commands import build_r_cmd as build_r_cmd_from_command_helpers
from hub_core.scaffold import DEFAULT_ANALYZE_R, normalize_scaffold_target_format, scaffold_project
from tests._symlink import symlink_or_skip
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT

HUB_ROOT = Path(__file__).resolve().parent.parent


class TestBuildRCmd(unittest.TestCase):
    def _config(self, r_strict: bool = False, include_environment: bool = True) -> dict:
        base: dict = {"project": {"name": "test"}}
        if include_environment:
            base["environment"] = {"r_strict": r_strict}
        return base

    def test_r_strict_false_returns_two_element_list(self):
        """r_strict=False produces [runner, script_path] with no extra args."""
        cmd = _build_r_cmd("Rscript", "/some/script.R", self._config(r_strict=False))
        self.assertEqual(cmd, ["Rscript", "/some/script.R"])

    def test_r_strict_true_contains_tryCatch(self):
        """r_strict=True wraps with renv::activate() and the third element contains tryCatch."""
        cmd = _build_r_cmd("Rscript", "/some/script.R", self._config(r_strict=True))
        self.assertEqual(len(cmd), 3)
        self.assertEqual(cmd[0], "Rscript")
        self.assertEqual(cmd[1], "-e")
        self.assertIn("tryCatch", cmd[2])

    def test_r_strict_true_single_quote_injection_escaped(self):
        """Paths containing single quotes are escaped so injection is not possible."""
        evil_path = "/some/path/with'quote/script.R"
        cmd = _build_r_cmd("Rscript", evil_path, self._config(r_strict=True))
        # The raw single-quote must not appear unescaped inside the expression
        expression = cmd[2]
        # After the opening source(' the next raw ' must not appear before closing )
        # Simplest check: the raw path fragment with unescaped ' is not in the expression
        self.assertNotIn("with'quote", expression)
        # The escaped variant must be present instead
        self.assertIn("with\\'quote", expression)

    def test_no_environment_key_in_config_defaults_to_r_strict_false(self):
        """Config without 'environment' key must not crash and returns 2-element list."""
        config = {"project": {"name": "test"}}
        cmd = _build_r_cmd("Rscript", "/script.R", config)
        self.assertEqual(cmd, ["Rscript", "/script.R"])

    def test_process_runner_reexports_command_helper(self):
        self.assertIs(_build_r_cmd, build_r_cmd_from_command_helpers)


class TestRunCommandRuntimeEnv(unittest.TestCase):
    def test_run_command_pins_uv_environment_outside_repo(self):
        captured = {}

        class FakeProcess:
            stdout = []
            returncode = 0

            def wait(self, timeout=None):
                return None

        def fake_popen(*_args, **kwargs):
            captured["env"] = kwargs["env"]
            return FakeProcess()

        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = str((Path(tmpdir) / "runtime").resolve())
            with (
                patch.dict(
                    os.environ,
                    {
                        "RESEARCH_HUB_RUNTIME_ROOT": runtime_root,
                        "UV_PROJECT_ENVIRONMENT": str(HUB_ROOT / ".venv"),
                    },
                    clear=False,
                ),
                patch("hub_core.process_runner.subprocess.Popen", side_effect=fake_popen),
            ):
                result = pr.run_command(["uv", "run", "python", "-V"], str(HUB_ROOT))

        self.assertTrue(result)
        self.assertEqual(
            captured["env"]["UV_PROJECT_ENVIRONMENT"],
            str(Path(runtime_root) / "uv_envs" / "figops"),
        )
        self.assertNotEqual(captured["env"]["UV_PROJECT_ENVIRONMENT"], str(HUB_ROOT / ".venv"))
        self.assertEqual(captured["env"]["UV_CACHE_DIR"], str(Path(runtime_root) / "uv_cache"))

    def test_run_command_rejects_reserved_additional_env_case_insensitively(self):
        with tempfile.TemporaryDirectory() as project_dir:
            for key in ("PROJECT_ROOT", "project_root", "PyThOnPaTh"):
                with self.subTest(key=key), patch("hub_core.process_runner.subprocess.Popen") as popen:
                    result = pr.run_command(
                        [sys.executable, "-c", "raise SystemExit(0)"],
                        project_dir,
                        additional_env={key: "attacker"},
                    )

                    self.assertFalse(result)
                    popen.assert_not_called()

    def test_run_command_replaces_case_variant_inherited_reserved_env(self):
        captured: dict[str, str] = {}

        class Completed:
            stdout: list[str] = []
            returncode = 0

            def wait(self, timeout=None):
                return self.returncode

        def fake_popen(_cmd, **kwargs):
            captured.update(kwargs["env"])
            return Completed()

        with tempfile.TemporaryDirectory() as project_dir:
            with (
                patch("hub_core.process_runner.os.environ.copy", return_value={"project_root": "attacker"}),
                patch("hub_core.process_runner.subprocess.Popen", side_effect=fake_popen),
            ):
                result = pr.run_command([sys.executable, "-c", "raise SystemExit(0)"], project_dir)

        matching_keys = [key for key in captured if key.upper() == "PROJECT_ROOT"]
        self.assertTrue(result)
        self.assertEqual(matching_keys, ["PROJECT_ROOT"])
        self.assertEqual(captured["PROJECT_ROOT"], os.path.abspath(project_dir))

    def test_run_command_times_out_silent_child_before_stdout_eof(self):
        with tempfile.TemporaryDirectory() as project_dir:
            started = time.monotonic()

            result = pr.run_command(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                project_dir,
                timeout_seconds=0.1,
            )

            elapsed = time.monotonic() - started

        self.assertFalse(result)
        self.assertLess(elapsed, 3.0)

    def test_run_command_logs_streamed_stdout_before_timeout(self):
        script = "import time; print('stream-before-timeout', flush=True); time.sleep(5)"
        with tempfile.TemporaryDirectory() as project_dir:
            started = time.monotonic()
            with self.assertLogs("hub_core.process_runner", level="INFO") as captured:
                result = pr.run_command(
                    [sys.executable, "-c", script],
                    project_dir,
                    timeout_seconds=1.0,
                )
            elapsed = time.monotonic() - started

        self.assertFalse(result)
        output = "\n".join(captured.output)
        self.assertIn("Execution timed out", output)
        self.assertIn("stream-before-timeout", output)
        self.assertLess(elapsed, 3.0)

    def test_run_command_retains_bounded_memory_for_high_output_failure(self):
        class Completed:
            returncode = 1

            def __init__(self):
                self.stdout = (f"{index:05d}-{'x' * 1024}\n" for index in range(20_000))

            def wait(self, timeout=None):
                return self.returncode

        tracemalloc.start()
        try:
            with (
                patch("hub_core.process_runner.subprocess.Popen", return_value=Completed()),
                patch("hub_core.process_runner._log", new=lambda _message="": None),
            ):
                result = pr.run_command([sys.executable, "-c", "raise SystemExit(1)"], tempfile.gettempdir())
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertFalse(result)
        self.assertLess(peak, 5_000_000)

    def test_run_command_retains_bounded_memory_for_high_output_without_newline(self):
        class NoNewlineStream:
            def __init__(self) -> None:
                self.remaining = 20_000_000

            def __iter__(self):
                yield "x" * self.remaining

            def read(self, size: int) -> str:
                if self.remaining == 0:
                    return ""
                chunk_size = min(size, self.remaining)
                self.remaining -= chunk_size
                return "x" * chunk_size

        class Completed:
            returncode = 1

            def __init__(self) -> None:
                self.stdout = NoNewlineStream()

            def wait(self, timeout=None):
                return self.returncode

        tracemalloc.start()
        try:
            with (
                patch("hub_core.process_runner.subprocess.Popen", return_value=Completed()),
                patch("hub_core.process_runner._log", new=lambda _message="": None),
            ):
                result = pr.run_command([sys.executable, "-c", "raise SystemExit(1)"], tempfile.gettempdir())
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertFalse(result)
        self.assertLess(peak, 5_000_000)

    def test_run_command_terminates_and_reaps_child_when_windows_job_assignment_fails(self):
        class FailedJob:
            def assign(self, _process):
                raise OSError("assignment rejected")

            def close(self):
                return None

        class StartedProcess:
            _handle = 123
            pid = 123
            returncode = None
            stdout: list[str] = []

            def __init__(self) -> None:
                self.killed = False
                self.wait_calls = 0

            def poll(self):
                return None if not self.killed else self.returncode

            def kill(self):
                self.killed = True
                self.returncode = 1

            def wait(self, timeout=None):
                self.wait_calls += 1
                return self.returncode

        process = StartedProcess()
        with (
            patch("hub_core.process_supervisor.os.name", "nt"),
            patch("hub_core.process_supervisor._WindowsProcessJob.create", return_value=FailedJob()),
            patch("hub_core.process_supervisor.subprocess.run"),
            patch("hub_core.process_runner.subprocess.Popen", return_value=process),
        ):
            result = pr.run_command([sys.executable, "-c", "raise SystemExit(0)"], tempfile.gettempdir())

        self.assertFalse(result)
        self.assertTrue(process.killed)
        self.assertGreaterEqual(process.wait_calls, 1)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object containment is Windows-specific")
    def test_run_command_kills_stdout_inheriting_orphan_descendant_on_timeout(self):
        with tempfile.TemporaryDirectory() as project_dir:
            marker = Path(project_dir, "orphan-descendant-marker.txt")
            grandchild_script = (
                "import time; from pathlib import Path; "
                f"time.sleep(0.75); Path({str(marker)!r}).write_text('escaped', encoding='utf-8')"
            )
            parent_script = (
                "import subprocess, sys; "
                f"subprocess.Popen([sys.executable, '-c', {grandchild_script!r}])"
            )
            started = time.monotonic()
            result = pr.run_command(
                [sys.executable, "-c", parent_script],
                project_dir,
                timeout_seconds=0.2,
            )
            elapsed = time.monotonic() - started
            time.sleep(1.0)
            descendant_survived = marker.exists()

        self.assertFalse(result)
        self.assertLess(elapsed, 3.0)
        self.assertFalse(descendant_survived, "stdout-inheriting orphan descendant survived the timeout")


class TestConfiguredTimeoutPropagation(unittest.TestCase):
    def test_analysis_passes_configured_timeout_to_run_command(self):
        with tempfile.TemporaryDirectory() as project_dir:
            Path(project_dir, "analysis.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            config = {
                "project": {"name": "analysis_timeout"},
                "environment": {},
                "execution": {"python": sys.executable, "timeout_seconds": 1.25},
                "language_policy": {"allow_nonstandard": True},
                "pipeline": {
                    "analysis": [
                        {"script": "analysis.py", "lang": "python", "outputs": [], "cache": False},
                    ]
                },
                "data_contract": {},
            }
            with patch("hub_core.process_runner.run_command", return_value=True) as run_command:
                result = run_analysis(
                    project_dir,
                    config,
                    {},
                    str(Path(project_dir, ".build_state.json")),
                    "hash",
                )

        self.assertTrue(result)
        self.assertEqual(run_command.call_args.kwargs["timeout_seconds"], 1.25)

    def test_batch_visual_passes_configured_timeout_to_run_command(self):
        with tempfile.TemporaryDirectory() as project_dir:
            Path(project_dir, "plot.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            config = {
                "project": {"name": "plot_timeout"},
                "environment": {},
                "execution": {"python": sys.executable, "timeout_seconds": 2.5},
                "language_policy": {"allow_nonstandard": True},
                "figures": [
                    {"id": "Fig1", "script": "plot.py", "output": "results/Fig1.png", "cache": False},
                ],
                "data_contract": {},
            }
            with (
                patch("hub_core.process_runner.run_command", return_value=True) as run_command,
                patch("hub_core.process_runner.verify_output_file", return_value=(True, "valid")),
            ):
                result = run_plots(
                    project_dir,
                    config,
                    {},
                    str(Path(project_dir, ".build_state.json")),
                    "hash",
                )

        self.assertTrue(result)
        self.assertEqual(run_command.call_args.kwargs["timeout_seconds"], 2.5)

    def test_each_visual_passes_configured_timeout_to_every_run_command(self):
        with tempfile.TemporaryDirectory() as project_dir:
            project_path = Path(project_dir)
            project_path.joinpath("plot.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            project_path.joinpath("raw").mkdir()
            project_path.joinpath("raw", "a.csv").write_text("x\n1\n", encoding="utf-8")
            project_path.joinpath("raw", "b.csv").write_text("x\n2\n", encoding="utf-8")
            config = {
                "project": {"name": "each_timeout"},
                "environment": {},
                "execution": {"python": sys.executable, "timeout_seconds": 3.75},
                "language_policy": {"allow_nonstandard": True},
                "figures": [
                    {
                        "id": "FigEach",
                        "script": "plot.py",
                        "inputs": ["raw/*.csv"],
                        "expand": "each",
                        "output": "results/{stem}.png",
                        "cache": False,
                    },
                ],
                "data_contract": {},
            }
            with (
                patch("hub_core.process_runner.run_command", return_value=True) as run_command,
                patch("hub_core.process_runner.verify_output_file", return_value=(True, "valid")),
            ):
                result = run_plots(
                    project_dir,
                    config,
                    {},
                    str(project_path / ".build_state.json"),
                    "hash",
                )

        self.assertTrue(result)
        self.assertEqual(run_command.call_count, 2)
        self.assertTrue(all(call.kwargs["timeout_seconds"] == 3.75 for call in run_command.call_args_list))

    def test_cached_batch_visual_rejects_corrupt_output_without_rerunning(self):
        with tempfile.TemporaryDirectory() as project_dir:
            Path(project_dir, "plot.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            config = {
                "project": {"name": "cached_batch"},
                "environment": {},
                "execution": {"python": sys.executable},
                "language_policy": {"allow_nonstandard": True},
                "figures": [{"id": "Fig1", "script": "plot.py", "output": "results/Fig1.png"}],
                "data_contract": {},
            }
            with (
                patch("hub_core.process_runner.is_step_stale", return_value=(False, "unchanged")),
                patch("hub_core.process_runner.verify_output_file", return_value=(False, "corrupt")) as verify_output,
                patch("hub_core.process_runner.run_command") as run_command,
            ):
                result = run_plots(project_dir, config, {}, str(Path(project_dir, ".build_state.json")), "hash")

        self.assertFalse(result)
        verify_output.assert_called_once()
        run_command.assert_not_called()

    def test_cached_each_visual_rejects_corrupt_output_without_rerunning(self):
        with tempfile.TemporaryDirectory() as project_dir:
            project_path = Path(project_dir)
            project_path.joinpath("plot.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            project_path.joinpath("raw").mkdir()
            project_path.joinpath("raw", "a.csv").write_text("x\n1\n", encoding="utf-8")
            config = {
                "project": {"name": "cached_each"},
                "environment": {},
                "execution": {"python": sys.executable},
                "language_policy": {"allow_nonstandard": True},
                "figures": [
                    {
                        "id": "FigEach",
                        "script": "plot.py",
                        "inputs": ["raw/*.csv"],
                        "expand": "each",
                        "output": "results/{stem}.png",
                    },
                ],
                "data_contract": {},
            }
            with (
                patch("hub_core.process_runner.is_step_stale", return_value=(False, "unchanged")),
                patch("hub_core.process_runner.verify_output_file", return_value=(False, "corrupt")) as verify_output,
                patch("hub_core.process_runner.run_command") as run_command,
            ):
                result = run_plots(project_dir, config, {}, str(project_path / ".build_state.json"), "hash")

        self.assertFalse(result)
        verify_output.assert_called_once()
        run_command.assert_not_called()


class TestScaffoldRAnalysisInputContract(unittest.TestCase):
    def _skip_without_rscript(self):
        if shutil.which("Rscript") is None:
            self.skipTest("Rscript is not installed")

    def _write_scaffold_analysis_project(self, project_dir: Path) -> dict:
        script_path = project_dir / "hub_scripts" / "analyze.R"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(DEFAULT_ANALYZE_R, encoding="utf-8")
        return {
            "project": {"name": "scaffold_r_contract"},
            "environment": {"r_strict": False},
            "pipeline": {
                "analysis": [
                    {
                        "script": "hub_scripts/analyze.R",
                        "lang": "r",
                        "inputs": ["raw/"],
                        "outputs": ["results/data/summary.csv"],
                    }
                ]
            },
            "data_contract": {},
        }

    def test_scaffold_r_analysis_reads_real_data_from_normalized_raw_dir(self):
        self._skip_without_rscript()

        with tempfile.TemporaryDirectory(prefix="graph_hub_r_inputs_") as tmpdir:
            project_dir = Path(tmpdir)
            raw_dir = project_dir / "raw"
            raw_dir.mkdir()
            (raw_dir / "measurement.csv").write_text(
                "time,value,molarity\n0,7.5,0.2\n1,8.5,0.3\n",
                encoding="utf-8",
            )
            config = self._write_scaffold_analysis_project(project_dir)

            result = run_analysis(
                str(project_dir),
                config,
                {},
                str(project_dir / ".build_state.json"),
                "config-hash",
                force=True,
            )

            self.assertTrue(result)
            with (project_dir / "results" / "data" / "summary.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["value"] for row in rows], ["7.5", "8.5"])

    def test_scaffold_r_analysis_fails_when_no_input_csv_exists(self):
        self._skip_without_rscript()

        with tempfile.TemporaryDirectory(prefix="graph_hub_r_no_inputs_") as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "raw").mkdir()
            config = self._write_scaffold_analysis_project(project_dir)

            result = run_analysis(
                str(project_dir),
                config,
                {},
                str(project_dir / ".build_state.json"),
                "config-hash",
                force=True,
            )

            self.assertFalse(result)
            self.assertFalse((project_dir / "results" / "data" / "summary.csv").exists())

    def test_scaffold_project_creates_normalized_raw_dir(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_scaffold_") as tmpdir:
            project_dir = Path(tmpdir) / "project"

            scaffold_project(project_dir, HUB_ROOT, project_name="raw_dir_contract")

            self.assertTrue((project_dir / "raw").is_dir())
            self.assertTrue((project_dir / "raw" / "example_input.csv").is_file())
            self.assertFalse((project_dir / "data" / "raw").exists())

    def test_scaffold_project_uses_packaged_template_when_root_template_is_absent(self):
        with tempfile.TemporaryDirectory(prefix="figops_packaged_scaffold_") as tmpdir:
            tmp_path = Path(tmpdir)
            hub_without_template = tmp_path / "installed_hub"
            project_dir = tmp_path / "project"
            packaged_template_dir = hub_without_template / "hub_core" / "templates"
            packaged_template_dir.mkdir(parents=True)
            packaged_template_dir.joinpath("project_config_template.yaml").write_text(
                Path("hub_core/templates/project_config_template.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            scaffold_project(project_dir, hub_without_template, project_name="Packaged Template Smoke")

            config_text = (project_dir / "project_config.yaml").read_text(encoding="utf-8")
            self.assertIn('name: "Packaged Template Smoke"', config_text)
            self.assertNotIn(INTERNAL_STYLE_TARGET_FORMAT, config_text)
            self.assertTrue((project_dir / "hub_scripts" / "plot.py").is_file())

    def test_scaffold_project_fails_fast_for_unrelated_hub_without_templates(self):
        with tempfile.TemporaryDirectory(prefix="figops_missing_scaffold_") as tmpdir:
            tmp_path = Path(tmpdir)
            unrelated_hub = tmp_path / "unrelated_hub"
            unrelated_hub.mkdir()

            with self.assertRaisesRegex(RuntimeError, "Missing scaffold template"):
                scaffold_project(tmp_path / "project", unrelated_hub, project_name="Should Fail")

    def test_scaffold_target_format_normalizes_valid_input(self):
        self.assertEqual(
            normalize_scaffold_target_format(" Nature ", {"nature", "science"}),
            "nature",
        )

    def test_scaffold_target_format_rejects_internal_placeholder(self):
        with self.assertRaisesRegex(ValueError, "Allowed values"):
            normalize_scaffold_target_format("internal", {"nature", INTERNAL_STYLE_TARGET_FORMAT, "science", "ppt"})


class TestRunSweepMonkeyPatch(unittest.TestCase):
    """Verify that run_sweep restores hub_core.process_runner.run_command after completion."""

    def test_run_command_restored_after_sweep(self):
        """run_command reference on the module is the original after run_sweep returns."""
        original_run_command = pr.run_command

        sweep_cfg = {
            "enabled": True,
            "parameter": "lr",
            "values": [0.01],
            "output_dir_pattern": "results/sweep_{parameter}_{value}",
        }
        config = {
            "project": {"name": "sweep_test"},
            "environment": {},
            "pipeline": {"analysis": []},
            "figures": [],
            "diagrams": [],
            "data_contract": {},
        }

        # Patch the three sub-functions called inside run_sweep so no filesystem ops occur
        with (
            patch("hub_core.process_runner.run_analysis", return_value=True),
            patch("hub_core.process_runner.run_plots", return_value=True),
            patch("hub_core.process_runner.run_diagrams", return_value=True),
            patch("hub_core.data_contract.validate_data_contract", return_value=True),
            patch("os.makedirs"),
        ):
            run_sweep(
                project_dir="/tmp/fake_project",
                config=config,
                build_state={},
                build_state_path="/tmp/fake_project/.build_state.json",
                config_hash="abc123",
                sweep_cfg=sweep_cfg,
            )

        self.assertIs(
            pr.run_command,
            original_run_command,
            "run_command was not restored after run_sweep completed",
        )

    def test_run_command_restored_even_when_run_fails(self):
        """run_command is restored via finally even when a sub-step fails."""
        original_run_command = pr.run_command

        sweep_cfg = {
            "enabled": True,
            "parameter": "lr",
            "values": [0.01],
            "output_dir_pattern": "results/sweep_{parameter}_{value}",
        }
        config = {
            "project": {"name": "sweep_fail_test"},
            "environment": {},
            "pipeline": {"analysis": []},
            "figures": [],
            "diagrams": [],
            "data_contract": {},
        }

        with (
            patch("hub_core.process_runner.run_analysis", return_value=False),
            patch("hub_core.process_runner.run_plots", return_value=True),
            patch("hub_core.process_runner.run_diagrams", return_value=True),
            patch("hub_core.data_contract.validate_data_contract", return_value=True),
            patch("os.makedirs"),
        ):
            result = run_sweep(
                project_dir="/tmp/fake_project",
                config=config,
                build_state={},
                build_state_path="/tmp/fake_project/.build_state.json",
                config_hash="abc123",
                sweep_cfg=sweep_cfg,
            )

        self.assertIs(pr.run_command, original_run_command)
        self.assertFalse(result)

    def test_run_sweep_does_not_replace_run_command_while_running(self):
        original_run_command = pr.run_command
        captured_env: dict[str, str] = {}

        class Completed:
            returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            @property
            def stdout(self):
                return []

        def fake_popen(_cmd, **kwargs):
            captured_env.update(kwargs["env"])
            return Completed()

        def fake_run_analysis(project_dir, *_args, **_kwargs):
            self.assertIs(pr.run_command, original_run_command)
            return pr.run_command(["analysis"], project_dir, additional_env={"EXTRA": "1"})

        sweep_cfg = {
            "enabled": True,
            "parameter": "lr",
            "values": [0.01],
            "output_dir_pattern": "results/sweep_{parameter}_{value}",
        }
        config = {
            "project": {"name": "sweep_runtime_test"},
            "environment": {},
            "pipeline": {"analysis": [{"script": "analysis.py"}]},
            "figures": [],
            "diagrams": [],
            "data_contract": {},
        }

        with (
            patch("hub_core.process_runner.run_analysis", side_effect=fake_run_analysis),
            patch("hub_core.process_runner.run_plots", return_value=True),
            patch("hub_core.process_runner.run_diagrams", return_value=True),
            patch("hub_core.process_runner.subprocess.Popen", side_effect=fake_popen),
            patch("hub_core.data_contract.validate_data_contract", return_value=True),
            patch("os.makedirs"),
        ):
            result = run_sweep(
                project_dir="/tmp/fake_project",
                config=config,
                build_state={},
                build_state_path="/tmp/fake_project/.build_state.json",
                config_hash="abc123",
                sweep_cfg=sweep_cfg,
            )

        self.assertTrue(result)
        self.assertIs(pr.run_command, original_run_command)
        self.assertEqual(captured_env["SWEEP_lr"], "0.01")
        self.assertEqual(captured_env["lr"], "0.01")
        self.assertEqual(captured_env["EXTRA"], "1")

    def test_run_comparison_does_not_replace_run_command_while_running(self):
        original_run_command = pr.run_command
        captured_env: dict[str, str] = {}

        class Completed:
            returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            @property
            def stdout(self):
                return []

        def fake_popen(_cmd, **kwargs):
            captured_env.update(kwargs["env"])
            return Completed()

        def fake_run_analysis(project_dir, *_args, **_kwargs):
            self.assertIs(pr.run_command, original_run_command)
            return pr.run_command(["analysis"], project_dir, additional_env={"EXTRA": "1"})

        comparison_cfg = {
            "enabled": True,
            "conditions": [
                {
                    "label": "control",
                    "env": {"dose": "low"},
                }
            ],
            "output_dir_pattern": "results/comparison_{condition}",
        }
        config = {
            "project": {"name": "comparison_runtime_test"},
            "environment": {},
            "pipeline": {"analysis": [{"script": "analysis.py"}]},
            "figures": [],
            "diagrams": [],
            "data_contract": {},
        }

        with (
            patch("hub_core.process_runner.run_analysis", side_effect=fake_run_analysis),
            patch("hub_core.process_runner.run_plots", return_value=True),
            patch("hub_core.process_runner.run_diagrams", return_value=True),
            patch("hub_core.process_runner.subprocess.Popen", side_effect=fake_popen),
            patch("hub_core.data_contract.validate_data_contract", return_value=True),
            patch("os.makedirs"),
        ):
            result = run_comparison(
                project_dir="/tmp/fake_project",
                config=config,
                build_state={},
                build_state_path="/tmp/fake_project/.build_state.json",
                config_hash="abc123",
                comparison_cfg=comparison_cfg,
            )

        self.assertTrue(result)
        self.assertIs(pr.run_command, original_run_command)
        self.assertEqual(captured_env["COMPARISON_dose"], "low")
        self.assertEqual(captured_env["dose"], "low")
        self.assertEqual(captured_env["COMPARISON_LABEL"], "control")
        self.assertEqual(captured_env["EXTRA"], "1")

    def test_run_sweep_injects_cache_env_overrides_and_unique_grid_outputs(self):
        """Grid sweeps should stamp env overrides into analysis cache keys and redirect outputs uniquely."""
        seen_configs: list[tuple[dict, str]] = []

        def fake_run_analysis(project_dir, run_config, *_args, **_kwargs):
            analysis_step = run_config["pipeline"]["analysis"][0]
            figure_output = run_config["figures"][0]["output"]
            seen_configs.append((dict(analysis_step["_cache_env_overrides"]), figure_output))
            return True

        sweep_cfg = {
            "enabled": True,
            "grid": {
                "temp": [300, 350],
                "voltage": [10, 20],
            },
            "output_dir_pattern": "results/{parameter}/{value}",
        }
        config = {
            "project": {"name": "grid_sweep_test"},
            "environment": {},
            "pipeline": {"analysis": [{"script": "analysis.py"}]},
            "figures": [{"output": "results/figures/Fig1.png"}],
            "diagrams": [],
            "data_contract": {},
        }

        with (
            patch("hub_core.process_runner.run_analysis", side_effect=fake_run_analysis),
            patch("hub_core.process_runner.run_plots", return_value=True),
            patch("hub_core.process_runner.run_diagrams", return_value=True),
            patch("hub_core.data_contract.validate_data_contract", return_value=True),
            patch("os.makedirs"),
        ):
            result = run_sweep(
                project_dir="/tmp/fake_project",
                config=config,
                build_state={},
                build_state_path="/tmp/fake_project/.build_state.json",
                config_hash="abc123",
                sweep_cfg=sweep_cfg,
            )

        self.assertTrue(result)
        self.assertEqual(len(seen_configs), 4)
        outputs = [output for _overrides, output in seen_configs]
        self.assertEqual(len(set(outputs)), 4)
        self.assertIn(
            "results/temp_voltage/temp_300_voltage_10/Fig1.png",
            outputs,
        )
        self.assertIn(
            "results/temp_voltage/temp_350_voltage_20/Fig1.png",
            outputs,
        )
        self.assertIn(
            {"temp": "300", "voltage": "10"},
            [overrides for overrides, _output in seen_configs],
        )
        self.assertIn(
            {"temp": "350", "voltage": "20"},
            [overrides for overrides, _output in seen_configs],
        )

    def test_run_sweep_reports_validate_stage_when_preflight_fails(self):
        failure_context = {}
        sweep_cfg = {
            "enabled": True,
            "parameter": "lr",
            "values": [0.01],
            "output_dir_pattern": "results/sweep_{parameter}_{value}",
        }
        config = {
            "project": {"name": "sweep_preflight_test"},
            "environment": {},
            "pipeline": {"analysis": []},
            "figures": [],
            "diagrams": [],
            "data_contract": {"csv_checks": [{"path": "results/data/output.csv"}]},
        }

        with (
            patch("hub_core.data_contract.validate_data_contract_preflight", return_value=False),
            patch("hub_core.process_runner.run_analysis") as run_analysis,
            patch("os.makedirs"),
        ):
            result = run_sweep(
                project_dir="/tmp/fake_project",
                config=config,
                build_state={},
                build_state_path="/tmp/fake_project/.build_state.json",
                config_hash="abc123",
                sweep_cfg=sweep_cfg,
                step="plot",
                failure_context=failure_context,
            )

        self.assertFalse(result)
        self.assertEqual(failure_context["stage"], "VALIDATE")
        self.assertIn("Sweep preflight failed", failure_context["message"])
        run_analysis.assert_not_called()

    def test_run_sweep_rejects_substituted_traversal_before_creating_outside_directory(self):
        with tempfile.TemporaryDirectory() as root_dir:
            project_dir = Path(root_dir, "project")
            project_dir.mkdir()
            outside_dir = Path(root_dir, "outside")
            failure_context: dict[str, str] = {}

            result = run_sweep(
                project_dir=str(project_dir),
                config={
                    "project": {"name": "substituted_traversal"},
                    "environment": {},
                    "pipeline": {"analysis": []},
                    "figures": [],
                    "diagrams": [],
                    "data_contract": {},
                },
                build_state={},
                build_state_path=str(project_dir / ".build_state.json"),
                config_hash="hash",
                sweep_cfg={
                    "enabled": True,
                    "parameter": "value",
                    "values": ["../../outside"],
                    "output_dir_pattern": "results/{value}",
                },
                step="analysis",
                failure_context=failure_context,
            )

            self.assertFalse(result)
            self.assertFalse(outside_dir.exists())
            self.assertEqual(failure_context["stage"], "CONFIG")

    def test_run_sweep_rejects_absolute_output_before_creation(self):
        with tempfile.TemporaryDirectory() as root_dir:
            project_dir = Path(root_dir, "project")
            project_dir.mkdir()
            outside_dir = Path(root_dir, "outside")
            failure_context: dict[str, str] = {}

            result = run_sweep(
                project_dir=str(project_dir),
                config={
                    "project": {"name": "absolute_output"},
                    "environment": {},
                    "pipeline": {"analysis": []},
                    "figures": [],
                    "diagrams": [],
                    "data_contract": {},
                },
                build_state={},
                build_state_path=str(project_dir / ".build_state.json"),
                config_hash="hash",
                sweep_cfg={
                    "enabled": True,
                    "parameter": "value",
                    "values": ["safe"],
                    "output_dir_pattern": str(outside_dir),
                },
                step="analysis",
                failure_context=failure_context,
            )

            self.assertFalse(result)
            self.assertFalse(outside_dir.exists())
            self.assertEqual(failure_context["stage"], "CONFIG")

    def test_run_sweep_rejects_output_through_outside_symlink(self):
        with tempfile.TemporaryDirectory() as root_dir:
            project_dir = Path(root_dir, "project")
            outside_dir = Path(root_dir, "outside")
            project_dir.mkdir()
            outside_dir.mkdir()
            symlink_or_skip(project_dir / "linked", outside_dir, target_is_directory=True)
            failure_context: dict[str, str] = {}

            result = run_sweep(
                project_dir=str(project_dir),
                config={
                    "project": {"name": "symlink_output"},
                    "environment": {},
                    "pipeline": {"analysis": []},
                    "figures": [],
                    "diagrams": [],
                    "data_contract": {},
                },
                build_state={},
                build_state_path=str(project_dir / ".build_state.json"),
                config_hash="hash",
                sweep_cfg={
                    "enabled": True,
                    "parameter": "value",
                    "values": ["safe"],
                    "output_dir_pattern": "linked/{value}",
                },
                step="analysis",
                failure_context=failure_context,
            )

            self.assertFalse(result)
            self.assertFalse(outside_dir.joinpath("safe").exists())
            self.assertEqual(failure_context["stage"], "CONFIG")

    def test_run_sweep_allows_contained_relative_output(self):
        with tempfile.TemporaryDirectory() as project_dir:
            result = run_sweep(
                project_dir=project_dir,
                config={
                    "project": {"name": "safe_output"},
                    "environment": {},
                    "pipeline": {"analysis": []},
                    "figures": [],
                    "diagrams": [],
                    "data_contract": {},
                },
                build_state={},
                build_state_path=str(Path(project_dir, ".build_state.json")),
                config_hash="hash",
                sweep_cfg={
                    "enabled": True,
                    "parameter": "value",
                    "values": ["safe"],
                    "output_dir_pattern": "results/{value}",
                },
                step="analysis",
            )

            self.assertTrue(result)
            self.assertTrue(Path(project_dir, "results", "safe").is_dir())

    def test_run_comparison_reports_validate_stage_when_preflight_fails(self):
        failure_context = {}
        comparison_cfg = {
            "enabled": True,
            "conditions": [
                {"label": "hot", "env": {"temp": "350"}},
            ],
        }
        config = {
            "project": {"name": "comparison_preflight_test"},
            "environment": {},
            "pipeline": {"analysis": []},
            "figures": [],
            "diagrams": [],
            "data_contract": {"csv_checks": [{"path": "results/data/output.csv"}]},
        }

        with (
            patch("hub_core.data_contract.validate_data_contract_preflight", return_value=False),
            patch("hub_core.process_runner.run_analysis") as run_analysis,
            patch("os.makedirs"),
        ):
            result = run_comparison(
                project_dir="/tmp/fake_project",
                config=config,
                build_state={},
                build_state_path="/tmp/fake_project/.build_state.json",
                config_hash="abc123",
                comparison_cfg=comparison_cfg,
                step="plot",
                failure_context=failure_context,
            )

        self.assertFalse(result)
        self.assertEqual(failure_context["stage"], "VALIDATE")
        self.assertIn("Comparison preflight failed", failure_context["message"])
        run_analysis.assert_not_called()


class TestSanitizerRejectedScriptFailsRun(unittest.TestCase):
    def test_rejected_plot_script_makes_run_fail(self):
        config = {
            "project": {"name": "sanitizer_reject_test"},
            "environment": {},
            "figures": [
                {"id": "Fig1", "script": "../../../etc/passwd.py", "output": "fig1.pdf"},
            ],
            "diagrams": [],
        }

        with tempfile.TemporaryDirectory() as project_dir:
            result = run_plots(
                project_dir=project_dir,
                config=config,
                build_state={},
                build_state_path=os.path.join(project_dir, ".build_state.json"),
                config_hash="abc123",
            )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
