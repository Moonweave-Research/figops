import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hub_core.error_dumper import dump_pipeline_failure
from hub_core.execution_log import write_execution_log
from hub_core.provenance import _prepare_dvc_env, _resolve_dvc_command
from hub_core.visual_regression import write_check_all_report


HUB_ROOT = Path(__file__).resolve().parent.parent


class RuntimePathTest(unittest.TestCase):
    def test_runtime_logs_and_reports_use_external_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()

            env = {
                "RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root),
                "RESEARCH_HUB_DVC_HOME": str(runtime_root / "dvc_home_override"),
            }

            config = {
                "project": {"name": "Runtime Test Project"},
                "execution": {},
            }

            with patch.dict(os.environ, env, clear=False):
                log_path, record = write_execution_log(
                    str(project_dir),
                    str(HUB_ROOT),
                    config,
                    str(project_dir / "project_config.yaml"),
                    "config-hash",
                    args={"step": "all"},
                    lock_info={"strict": False, "python_lock": {}, "r_lock": {}},
                    dvc_info={"enabled": True, "status": "ok", "status_hash": "abc"},
                    build_state_path=str(project_dir / ".build_state.json"),
                    start_time=None,
                    end_time=None,
                    success=True,
                )
                report_path = write_check_all_report(
                    str(HUB_ROOT),
                    {"schema_version": 3, "success": True, "results": []},
                )
                dvc_env = _prepare_dvc_env(str(HUB_ROOT))

            self.assertTrue(Path(log_path).is_file())
            self.assertTrue(Path(report_path).is_file())
            self.assertTrue(str(Path(log_path)).startswith(str(runtime_root)))
            self.assertTrue(str(Path(report_path)).startswith(str(runtime_root)))
            self.assertEqual(dvc_env["DVC_HOME"], str(runtime_root / "dvc_home_override"))
            self.assertEqual(dvc_env["XDG_CACHE_HOME"], str(runtime_root / "dvc_home_override" / "xdg_cache"))
            self.assertEqual(dvc_env["XDG_CONFIG_HOME"], str(runtime_root / "dvc_home_override" / "xdg_config"))
            self.assertEqual(dvc_env["XDG_STATE_HOME"], str(runtime_root / "dvc_home_override" / "xdg_state"))
            self.assertEqual(record["status"], "success")
            self.assertEqual(record["project_name"], "Runtime Test Project")
            self.assertEqual(record["job_id"], "project")
            self.assertEqual(record["engine_target"], "hub_pipeline")
            self.assertEqual(record["failure_stage"], "")
            self.assertIn("request", record)
            self.assertEqual(record["request"]["raw_request"], "python orchestrator.py --step all")

            manifest_path = Path(record["artifacts_dir"]) / "manifest.json"
            status_path = Path(record["artifacts_dir"]) / "status.json"
            latest_manifest_path = Path(record["latest_dir"]) / "manifest.json"
            latest_status_path = Path(record["latest_dir"]) / "status.json"

            self.assertTrue(manifest_path.is_file())
            self.assertTrue(status_path.is_file())
            self.assertTrue(latest_manifest_path.is_file())
            self.assertTrue(latest_status_path.is_file())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            status = json.loads(status_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["engine_target"], "hub_pipeline")
            self.assertEqual(manifest["job_id"], "project")
            self.assertEqual(manifest["request"]["raw_request"], "python orchestrator.py --step all")
            self.assertTrue(manifest["result"]["success"])
            self.assertEqual(status["status"], "success")
            self.assertEqual(status["job_id"], "project")

    def test_failure_dump_includes_common_execution_fields(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_failure_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()

            failure_path = dump_pipeline_failure(
                str(project_dir),
                message="Plotting step failed.",
                context={
                    "raw_request": "python orchestrator.py --project demo --step plot",
                    "engine_target": "hub_pipeline",
                    "job_id": "project",
                    "failure_stage": "EXECUTE",
                },
            )

            payload = json.loads(Path(failure_path).read_text(encoding="utf-8"))
            latest_failure = Path(payload["latest_dir"]) / "failure.json"

            self.assertEqual(payload["engine_target"], "hub_pipeline")
            self.assertEqual(payload["job_id"], "project")
            self.assertEqual(payload["failure_stage"], "EXECUTE")
            self.assertEqual(
                payload["request"]["raw_request"],
                "python orchestrator.py --project demo --step plot",
            )
            self.assertTrue(latest_failure.is_file())

    def test_resolve_dvc_command_falls_back_when_no_candidate_works(self):
        attempted = []

        def fake_is_executable_available(cmd):
            attempted.append(cmd)
            return cmd in {"dvc", sys.executable}

        class Result:
            def __init__(self, returncode):
                self.returncode = returncode
                self.stdout = ""

        def fake_run(cmd, **kwargs):
            return Result(1)

        with patch("hub_core.provenance.is_executable_available", side_effect=fake_is_executable_available):
            with patch("hub_core.provenance.subprocess.run", side_effect=fake_run):
                command = _resolve_dvc_command()

        self.assertIsNone(command)
        self.assertIn("dvc", attempted)
        self.assertIn(sys.executable, attempted)
        
        expected_venv_dvc = str(HUB_ROOT / ".venv" / "bin" / "dvc")
        self.assertIn(expected_venv_dvc, attempted)

    def test_resolve_dvc_command_prefers_sibling_dvc_of_python(self):
        sibling_dvc = str(HUB_ROOT / ".venv" / "bin" / "dvc")

        def fake_is_executable_available(cmd):
            return cmd in {sibling_dvc, "dvc", sys.executable}

        class Result:
            def __init__(self, returncode):
                self.returncode = returncode
                self.stdout = ""

        def fake_run(cmd, **kwargs):
            return Result(0 if cmd and cmd[0] == sibling_dvc else 1)

        with patch("hub_core.provenance.os.path.exists", side_effect=lambda p: p == sibling_dvc):
            with patch("hub_core.provenance.is_executable_available", side_effect=fake_is_executable_available):
                with patch("hub_core.provenance.subprocess.run", side_effect=fake_run):
                    command = _resolve_dvc_command()

        self.assertEqual(command, [sibling_dvc])


if __name__ == "__main__":
    unittest.main()
