import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt

import hub_core.process_runner as pr
import orchestrator
from hub_core.athena_bridge import AthenaBridge
from hub_core.cache_manager import load_build_state
from hub_core.config_parser import load_config
from hub_core.data_contract import validate_data_contract, validate_data_contract_preflight
from hub_core.docker_runner import rerun_in_docker
from hub_core.error_dumper import dump_contract_report
from hub_core.execution_log import append_execution_log
from hub_core.logging import configure_logging, get_logger
from hub_core.mcp import GraphHubMCPServer, run_stdio_server
from hub_core.provenance import embed_figures_fingerprint, print_provenance, validate_environment_locks
from hub_core.ui_utils import ui_panel, ui_print, ui_table
from hub_core.visual_regression import write_check_all_report


class TestGraphHubLogging(unittest.TestCase):
    def tearDown(self) -> None:
        configure_logging("WARNING")

    def test_configure_logging_honors_env_level_and_writes_to_stderr(self):
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"GRAPH_HUB_LOG_LEVEL": "DEBUG"}, clear=False),
            contextlib.redirect_stderr(stderr),
        ):
            configure_logging()
            get_logger("tests.graphhub.logging").debug("debug log is visible")

        self.assertIn("debug log is visible", stderr.getvalue())

    def test_process_runner_logs_progress_to_stderr_not_stdout(self):
        config = {
            "project": {"name": "logging_test"},
            "environment": {},
            "pipeline": {"analysis": []},
            "data_contract": {},
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            configure_logging("INFO")
            result = pr.run_analysis(
                project_dir="/tmp/graphhub_logging_test",
                config=config,
                build_state={},
                build_state_path="/tmp/graphhub_logging_test/.build_state.json",
                config_hash="config-hash",
            )

        self.assertTrue(result)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Analysis Step] logging_test", stderr.getvalue())
        self.assertIn("(No analysis steps defined)", stderr.getvalue())

    def test_mcp_stdio_logging_stays_off_framed_stdout(self):
        class LoggingServer(GraphHubMCPServer):
            def call_tool(self, name, arguments):
                get_logger("tests.graphhub.mcp").warning("LOG_WOULD_CORRUPT_WIRE")
                return super().call_tool(name, arguments)

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "graphhub.health", "arguments": {}},
            }
        ).encode("utf-8")
        input_stream = io.BytesIO(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
        output_stream = io.BytesIO()
        process_stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(process_stdout), contextlib.redirect_stderr(stderr):
            configure_logging("DEBUG")
            rc = run_stdio_server(LoggingServer(), input_stream=input_stream, output_stream=output_stream)

        self.assertEqual(rc, 0)
        raw_output = output_stream.getvalue()
        self.assertIn(b"Content-Length:", raw_output)
        self.assertNotIn(b"LOG_WOULD_CORRUPT_WIRE", raw_output)
        self.assertEqual("", process_stdout.getvalue())
        self.assertIn("LOG_WOULD_CORRUPT_WIRE", stderr.getvalue())

    def test_cache_manager_warnings_log_to_stderr_not_stdout(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_logging_cache_") as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".build_state.json").write_text("{not json", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                state, state_path = load_build_state(str(project_dir))

        self.assertEqual("", stdout.getvalue())
        self.assertIn("invalid build state", stderr.getvalue())
        self.assertEqual(state_path, str(project_dir / ".build_state.json"))
        self.assertEqual(state["version"], 4)

    def test_execution_log_status_logs_to_stderr_not_stdout(self):
        record = {"status": "success", "schema_version": 1}
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_exec_") as tmpdir:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                log_path = append_execution_log(
                    hub_path=tmpdir,
                    record=record,
                    log_dirname=tmpdir,
                    filename="execution.jsonl",
                )
            self.assertTrue(Path(log_path).exists())

        self.assertEqual("", stdout.getvalue())
        self.assertIn("Execution log appended", stderr.getvalue())

    def test_visual_regression_report_status_logs_to_stderr_not_stdout(self):
        report = {
            "schema_version": 3,
            "success": True,
            "results": [],
            "project_count": 0,
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_report_") as tmpdir:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                report_path = write_check_all_report(tmpdir, report, log_dirname=tmpdir)
            self.assertTrue(Path(report_path).exists())

        self.assertEqual("", stdout.getvalue())
        self.assertIn("Check-all report written", stderr.getvalue())

    def test_data_contract_preflight_logs_to_stderr_not_stdout(self):
        config = {"data_contract": {"csv_checks": [{"path": "results/data/summary.csv"}]}}
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_contract_preflight_") as tmpdir:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                result = validate_data_contract_preflight(tmpdir, config)

        self.assertTrue(result)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Data Contract Preflight]", stderr.getvalue())

    def test_data_contract_validation_logs_to_stderr_not_stdout(self):
        config = {"data_contract": {"csv_checks": [{"path": "summary.csv", "required_columns": ["value"]}]}}
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_contract_") as tmpdir:
            Path(tmpdir, "summary.csv").write_text("value\n1\n2\n", encoding="utf-8")
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                result = validate_data_contract(tmpdir, config)

        self.assertTrue(result)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Data Contract Step]", stderr.getvalue())

    def test_environment_lock_gate_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_lock_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            hub_dir = Path(tmpdir) / "hub"
            project_dir.mkdir()
            hub_dir.mkdir()
            config = {"environment": {}}

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                result = validate_environment_locks(str(project_dir), str(hub_dir), config, strict_cli=False)

        self.assertTrue(result["ok"])
        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Environment Lock Gate]", stderr.getvalue())
        self.assertIn("Lockfile missing", stderr.getvalue())

    def test_print_provenance_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_provenance_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            config_path = project_dir / "project_config.yaml"
            project_dir.mkdir()
            config_path.write_text("project:\n  name: logging\n", encoding="utf-8")

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                print_provenance(str(project_dir), str(config_path), "abc123", {"execution": {}})

        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Provenance]", stderr.getvalue())
        self.assertIn("config_hash:", stderr.getvalue())

    def test_figure_fingerprint_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_fingerprint_") as tmpdir:
            project_dir = Path(tmpdir)
            figures_dir = project_dir / "results" / "figures"
            figures_dir.mkdir(parents=True)
            (figures_dir / "unregistered.svg").write_text(
                '<svg height="10" width="10"><circle cx="5" cy="5" r="4" /></svg>',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                embedded = embed_figures_fingerprint(
                    str(project_dir),
                    {"project": {"name": "logging"}, "figures": [], "diagrams": []},
                    "config-hash",
                    "env-hash",
                    "git-sha",
                    "2026-06-19T00:00:00",
                )

        self.assertEqual(1, embedded)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("unregistered figure(s)", stderr.getvalue())
        self.assertIn("[Digital Fingerprint] 1 file(s) tagged", stderr.getvalue())

    def test_missing_project_config_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_config_missing_") as tmpdir:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                config, config_path, config_hash = load_config(tmpdir)

        self.assertIsNone(config)
        self.assertIsNone(config_path)
        self.assertIsNone(config_hash)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("project_config.yaml not found", stderr.getvalue())

    def test_invalid_project_config_yaml_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_config_yaml_") as tmpdir:
            Path(tmpdir, "project_config.yaml").write_text("project: [\n", encoding="utf-8")
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                config, config_path, config_hash = load_config(tmpdir)

        self.assertIsNone(config)
        self.assertIsNone(config_path)
        self.assertIsNone(config_hash)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("Invalid YAML", stderr.getvalue())

    def test_invalid_project_config_schema_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_config_schema_") as tmpdir:
            Path(tmpdir, "project_config.yaml").write_text("project: {}\n", encoding="utf-8")
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                config, config_path, config_hash = load_config(tmpdir)

        self.assertIsNone(config)
        self.assertIsNone(config_path)
        self.assertIsNone(config_hash)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("Invalid config schema", stderr.getvalue())

    def test_docker_runner_status_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        proc = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_docker_") as tmpdir:
            with (
                patch("hub_core.docker_runner.shutil.which", return_value="/usr/bin/docker"),
                patch("hub_core.docker_runner.subprocess.run", return_value=proc),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                configure_logging("INFO")
                rc = rerun_in_docker(tmpdir, tmpdir, [], build=True)

        self.assertEqual(0, rc)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Docker Build]", stderr.getvalue())
        self.assertIn("[Docker Mode]", stderr.getvalue())

    def test_docker_runner_timeout_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_docker_timeout_") as tmpdir:
            with (
                patch("hub_core.docker_runner.shutil.which", return_value="/usr/bin/docker"),
                patch(
                    "hub_core.docker_runner.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=3600),
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                configure_logging("INFO")
                rc = rerun_in_docker(tmpdir, tmpdir, [])

        self.assertEqual(1, rc)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("Docker run timed out", stderr.getvalue())

    def test_contract_report_status_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        violations = [
            {
                "row": "1",
                "column": "value",
                "value": "bad",
                "expected": "numeric",
                "violation_type": "type",
            }
        ]

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_contract_report_") as tmpdir:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                configure_logging("INFO")
                report_path = dump_contract_report(tmpdir, "results/data/summary.csv", violations)
            self.assertIsNotNone(report_path)
            self.assertTrue(Path(report_path).exists())

        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Contract Violations] Report saved", stderr.getvalue())

    def test_ui_helpers_write_human_output_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            ui_print("plain status")
            ui_panel("panel body", title="Panel")
            ui_table("Table", ["Name"], [["alpha"]])

        self.assertEqual("", stdout.getvalue())
        stderr_text = stderr.getvalue()
        self.assertIn("plain status", stderr_text)
        self.assertIn("panel body", stderr_text)
        self.assertIn("alpha", stderr_text)

    def test_athena_bridge_engine_errors_log_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        bridge = AthenaBridge()
        bridge._engine = None

        with (
            tempfile.TemporaryDirectory(prefix="graphhub_logging_missing_athena_") as tmpdir,
            patch.dict(os.environ, {"ATHENA_PATH": str(Path(tmpdir) / "missing")}, clear=False),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            configure_logging("INFO")
            loaded = bridge.load_engine()

        self.assertFalse(loaded)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("Athena root not found", stderr.getvalue())

    def test_athena_bridge_import_failure_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        bridge = AthenaBridge()
        bridge._engine = None

        with (
            tempfile.TemporaryDirectory(prefix="graphhub_logging_bad_athena_") as tmpdir,
            patch.dict(os.environ, {"ATHENA_PATH": tmpdir}, clear=False),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            configure_logging("INFO")
            loaded = bridge.load_engine()

        self.assertFalse(loaded)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("Linked to engine", stderr.getvalue())
        self.assertIn("Failed to import engine components", stderr.getvalue())

    def test_athena_bridge_render_success_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        bridge = AthenaBridge()
        original_engine = bridge._engine
        fig, ax = plt.subplots()

        try:
            bridge._engine = {
                "build_device_figure": lambda **kwargs: (fig, ax, {}),
            }
            with tempfile.TemporaryDirectory(prefix="graphhub_logging_athena_render_") as tmpdir:
                output_path = Path(tmpdir) / "fig.png"
                with (
                    patch.object(bridge, "load_engine", return_value=True),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    configure_logging("INFO")
                    rendered = bridge.render({"layers": []}, str(output_path))
                self.assertTrue(output_path.exists())
        finally:
            bridge._engine = original_engine
            plt.close(fig)

        self.assertTrue(rendered)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("Rendered: fig.png", stderr.getvalue())

    def test_orchestrator_athena_health_hook_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        proc = MagicMock(returncode=0)

        with (
            patch("orchestrator.subprocess.run", return_value=proc),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            configure_logging("INFO")
            orchestrator.run_athena_health_hook("/tmp/research-root", "/tmp/hub")

        self.assertEqual("", stdout.getvalue())
        self.assertIn("Athena Health", stderr.getvalue())

    def test_orchestrator_cli_preset_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        config = {"presets": {"paper": {"target_format": "nature"}}, "visual_style": {}}

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            configure_logging("INFO")
            orchestrator._apply_cli_preset(config, "paper")

        self.assertEqual("nature", config["visual_style"]["target_format"])
        self.assertEqual("", stdout.getvalue())
        self.assertIn("--preset 'paper' applied", stderr.getvalue())

    def test_orchestrator_check_all_summary_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        report = {
            "success": True,
            "project_count": 1,
            "discovered_count": 1,
            "invalid_count": 0,
            "passed_count": 1,
            "failed_count": 0,
        }

        with (
            patch.object(sys, "argv", ["orchestrator.py", "--check-all", "--verbose"]),
            patch("orchestrator.run_preflight_check"),
            patch("orchestrator.run_check_all", return_value=("/tmp/check-all.json", report)),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            rc = orchestrator.main()

        self.assertEqual(0, rc)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Check-All Summary]", stderr.getvalue())
        self.assertIn("report_path: /tmp/check-all.json", stderr.getvalue())

    def test_orchestrator_no_projects_error_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(sys, "argv", ["orchestrator.py"]),
            patch("orchestrator.run_preflight_check"),
            patch("orchestrator.get_discoverable_projects", return_value=[]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            rc = orchestrator.main()

        self.assertEqual(1, rc)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("No configured projects found", stderr.getvalue())

    def test_orchestrator_missing_project_error_logs_to_stderr_not_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory(prefix="graphhub_logging_missing_project_") as tmpdir:
            with (
                patch.object(sys, "argv", ["orchestrator.py", "--project", "missing"]),
                patch("orchestrator.get_research_root", return_value=tmpdir),
                patch("orchestrator.run_preflight_check"),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                rc = orchestrator.main()

        self.assertEqual(1, rc)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("Project directory not found", stderr.getvalue())
