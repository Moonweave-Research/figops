"""Unit tests for _build_r_cmd and run_sweep in hub_core.process_runner."""

import csv
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hub_core.process_runner as pr
from hub_core.process_runner import _build_r_cmd, run_analysis, run_comparison, run_plots, run_sweep
from hub_core.scaffold import DEFAULT_ANALYZE_R, scaffold_project

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
