import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hub_core.error_dumper import dump_pipeline_failure
from hub_core.execution_log import write_execution_log
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
                    build_state_path=str(project_dir / ".build_state.json"),
                    start_time=None,
                    end_time=None,
                    success=True,
                )
                report_path = write_check_all_report(
                    str(HUB_ROOT),
                    {"schema_version": 3, "success": True, "results": []},
                )

            self.assertTrue(Path(log_path).is_file())
            self.assertTrue(Path(report_path).is_file())
            self.assertTrue(str(Path(log_path)).startswith(str(runtime_root)))
            self.assertTrue(str(Path(report_path)).startswith(str(runtime_root)))
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


if __name__ == "__main__":
    unittest.main()
