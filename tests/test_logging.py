import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

import hub_core.process_runner as pr
from hub_core.logging import configure_logging, get_logger
from hub_core.mcp import GraphHubMCPServer, run_stdio_server


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
