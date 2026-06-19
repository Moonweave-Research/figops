import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hub_core.process_runner as pr
from hub_core.cache_manager import load_build_state
from hub_core.execution_log import append_execution_log
from hub_core.logging import configure_logging, get_logger
from hub_core.mcp import GraphHubMCPServer, run_stdio_server
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
