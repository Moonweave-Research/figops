import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hub_core.error_dumper import dump_pipeline_failure
from hub_core.execution_log import write_execution_log
from hub_core.runtime_paths import preview_runtime_root, resolve_runtime_root
from hub_core.visual_regression import write_check_all_report

HUB_ROOT = Path(__file__).resolve().parent.parent


class RuntimePathTest(unittest.TestCase):
    def test_preview_runtime_root_does_not_create_directory(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = Path(tmpdir) / "preview-only"

            with patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)}, clear=False):
                preview = preview_runtime_root()

            self.assertEqual(Path(preview), runtime_root)
            self.assertFalse(runtime_root.exists())

    def test_preview_runtime_root_preserves_nested_override_without_creating(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            runtime_root = Path(tmpdir) / "new" / "nested" / "runtime" / "root"

            with patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)}, clear=False):
                preview = preview_runtime_root()
                self.assertEqual(Path(preview), runtime_root)
                self.assertFalse(runtime_root.exists())
                self.assertFalse(runtime_root.parent.exists())
                resolved = resolve_runtime_root()

            self.assertEqual(Path(resolved), runtime_root)
            self.assertTrue(runtime_root.is_dir())

    def test_preview_runtime_root_matches_resolver_fallback_without_creating(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            blocked_cache = Path(tmpdir) / "cache-file"
            blocked_cache.write_text("not a directory", encoding="utf-8")
            fallback_root = Path(tmpdir) / "graph_making_hub_runtime"

            with (
                patch.dict(
                    os.environ,
                    {"RESEARCH_HUB_RUNTIME_ROOT": "", "RESEARCH_HUB_RUNTIME_HOME": "", "TMPDIR": tmpdir},
                    clear=False,
                ),
                patch("hub_core.runtime_paths._default_user_cache_dir", return_value=str(blocked_cache)),
                patch("hub_core.runtime_paths.tempfile.gettempdir", return_value=tmpdir),
            ):
                preview = preview_runtime_root()
                self.assertEqual(Path(preview), fallback_root)
                self.assertFalse(fallback_root.exists())
                resolved = resolve_runtime_root()

            self.assertEqual(Path(resolved), fallback_root)
            self.assertTrue(fallback_root.is_dir())

    def test_preview_runtime_root_fallback_does_not_probe_tempdir(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            blocked_cache = Path(tmpdir) / "cache-file"
            blocked_cache.write_text("not a directory", encoding="utf-8")
            preview_tmp = Path(tmpdir) / "preview-temp"
            fallback_root = preview_tmp / "graph_making_hub_runtime"

            with (
                patch.dict(
                    os.environ,
                    {
                        "RESEARCH_HUB_RUNTIME_ROOT": "",
                        "RESEARCH_HUB_RUNTIME_HOME": "",
                        "TMPDIR": str(preview_tmp),
                    },
                    clear=False,
                ),
                patch("hub_core.runtime_paths._default_user_cache_dir", return_value=str(blocked_cache)),
                patch("hub_core.runtime_paths.tempfile.gettempdir", side_effect=FileNotFoundError("probe disallowed")),
            ):
                preview = preview_runtime_root()

            self.assertEqual(Path(preview), fallback_root)
            self.assertFalse(fallback_root.exists())

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
