import json
import os
import tempfile
import unittest
from base64 import b64encode
from pathlib import Path
from unittest.mock import patch

from hub_core.attempt_provenance import build_attempt_provenance
from hub_core.error_dumper import dump_exception_failure, dump_pipeline_failure
from hub_core.execution_log import write_execution_log
from hub_core.redaction import redact_secrets, redact_text
from hub_core.runtime_paths import preview_runtime_root, resolve_runtime_root
from hub_core.visual_regression import write_check_all_report

HUB_ROOT = Path(__file__).resolve().parent.parent


class RuntimePathTest(unittest.TestCase):
    def test_unresolved_home_marker_never_creates_repo_local_tilde_runtime(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("hub_core.runtime_paths.os.path.expanduser", side_effect=lambda value: value),
                patch("hub_core.runtime_paths.tempfile.gettempdir", return_value=tmpdir),
            ):
                resolved = resolve_runtime_root()

            self.assertTrue(Path(resolved).is_relative_to(Path(tmpdir)))
            self.assertNotIn("~", Path(resolved).parts)

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

    def test_graph_hub_runtime_root_is_honored_after_research_overrides(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            research_root = Path(tmpdir) / "research-root"
            research_home = Path(tmpdir) / "research-home"
            graph_root = Path(tmpdir) / "graph-root"

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_HUB_RUNTIME_ROOT": str(research_root),
                    "RESEARCH_HUB_RUNTIME_HOME": str(research_home),
                    "GRAPH_HUB_RUNTIME_ROOT": str(graph_root),
                },
                clear=False,
            ):
                self.assertEqual(Path(preview_runtime_root()), research_root)

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_HUB_RUNTIME_ROOT": "",
                    "RESEARCH_HUB_RUNTIME_HOME": str(research_home),
                    "GRAPH_HUB_RUNTIME_ROOT": str(graph_root),
                },
                clear=False,
            ):
                self.assertEqual(Path(preview_runtime_root()), research_home)

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_HUB_RUNTIME_ROOT": "",
                    "RESEARCH_HUB_RUNTIME_HOME": "",
                    "GRAPH_HUB_RUNTIME_ROOT": str(graph_root),
                },
                clear=False,
            ):
                preview = preview_runtime_root()
                resolved = resolve_runtime_root()

            self.assertEqual(Path(preview), graph_root)
            self.assertEqual(Path(resolved), graph_root)
            self.assertTrue(graph_root.is_dir())

    def test_preview_runtime_root_matches_resolver_fallback_without_creating(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_runtime_") as tmpdir:
            blocked_cache = Path(tmpdir) / "cache-file"
            blocked_cache.write_text("not a directory", encoding="utf-8")
            fallback_root = Path(tmpdir) / "figops_runtime"

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
            fallback_root = preview_tmp / "figops_runtime"

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

    def test_failure_dump_redacts_nested_secrets_and_keeps_safe_context(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_failure_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            secret = "task3-secret-sentinel"

            failure_path = dump_pipeline_failure(
                str(project_dir),
                message=f"failed with token={secret}",
                context={
                    "safe_stage": "VALIDATE",
                    "password": secret,
                    "nested": {
                        "authorization": f"Bearer {secret}",
                        "url": f"https://user:{secret}@example.test/path",
                    },
                },
            )

            payload_text = Path(failure_path).read_text(encoding="utf-8")
            payload = json.loads(payload_text)
            latest_text = (Path(payload["latest_dir"]) / "failure.json").read_text(encoding="utf-8")

            self.assertNotIn(secret, payload_text)
            self.assertNotIn(secret, latest_text)
            self.assertEqual(payload["context"]["safe_stage"], "VALIDATE")

    def test_exception_dump_disables_unallowlisted_locals_by_default(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_failure_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            secret = "task3-local-secret-sentinel"

            def raise_with_secret() -> None:
                local_token = secret
                raise RuntimeError(f"authorization=Bearer {local_token}")

            try:
                raise_with_secret()
            except RuntimeError as exc:
                failure_path = dump_exception_failure(str(project_dir), exc)

            payload = json.loads(Path(failure_path).read_text(encoding="utf-8"))
            self.assertNotIn(secret, json.dumps(payload))
            self.assertTrue(all(not frame["locals"] for frame in payload["traceback_tail"]))

    def test_attempt_provenance_exposes_minimum_cli_contract(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_attempt_") as tmpdir:
            config_path = Path(tmpdir) / "project_config.yaml"
            config_path.write_text("project: {name: demo}\n", encoding="utf-8")

            attempt = build_attempt_provenance(
                surface="cli",
                step="plot",
                selector_kind="project",
                hub_path=str(HUB_ROOT),
                config_path=config_path,
            )

            self.assertEqual(attempt["surface"], "cli")
            self.assertEqual(attempt["step"], "plot")
            self.assertEqual(attempt["config_status"], "valid")
            self.assertRegex(attempt["raw_config_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(attempt["environment_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(attempt["git_commit"], r"^[0-9a-f]{40}$")

    def test_execution_record_persists_attempt_provenance(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_attempt_record_") as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            attempt = {
                "attempt_id": "attempt-1",
                "surface": "cli",
                "config_status": "missing",
                "unavailable_fields": ["raw_config_sha256"],
            }

            with patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)}, clear=False):
                _log_path, record = write_execution_log(
                    str(project_dir),
                    str(HUB_ROOT),
                    {"project": {"name": "Attempt Project"}},
                    None,
                    None,
                    success=False,
                    attempt_provenance=attempt,
                )

            manifest = json.loads((Path(record["artifacts_dir"]) / "manifest.json").read_text(encoding="utf-8"))
            status = json.loads((Path(record["artifacts_dir"]) / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(record["attempt_provenance"], attempt)
            self.assertEqual(manifest["attempt_provenance"], attempt)
            self.assertEqual(status["attempt_provenance"], attempt)

    def test_text_redaction_masks_quoted_json_basic_auth_and_uri_query_credentials(self):
        secret = "task3-json-secret-sentinel"
        basic = b64encode(f"user:{secret}".encode("utf-8")).decode("ascii")
        raw_text = (
            f'{{"token":"{secret}", "password" : "{secret}"}} '
            f"Authorization: Basic {basic} "
            f"https://user:{secret}@example.test/path?api_key={secret}&safe=retained"
        )

        redacted = redact_text(raw_text)
        safe_context = redact_secrets({"stage": "VALIDATE", "url": raw_text})

        self.assertNotIn(secret, redacted)
        self.assertNotIn(basic, redacted)
        self.assertIn("safe=retained", redacted)
        self.assertEqual(safe_context["stage"], "VALIDATE")
        self.assertNotIn(secret, safe_context["url"])

    def test_redaction_masks_exact_sensitive_keys_without_hiding_style_token_metadata(self):
        # Given: a mixed diagnostics payload with credentials and harmless geometry metadata.
        payload = {
            "token": "task3-exact-token-sentinel",
            "api_key": "task3-api-key-sentinel",
            "password": "task3-password-sentinel",
            "token_sizes": [6.0, 7.0],
            "style_token": "axis_label",
        }

        # When: redacting a persisted diagnostics payload.
        redacted = redact_secrets(payload)
        traceback_text = "raise RuntimeError('token=task3-traceback-sentinel')"
        redacted_traceback = redact_text(traceback_text)

        # Then: only actual credential fields are masked.
        self.assertEqual(redacted["token"], "[REDACTED]")
        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["token_sizes"], [6.0, 7.0])
        self.assertEqual(redacted["style_token"], "axis_label")
        self.assertNotIn("task3-traceback-sentinel", redacted_traceback)


if __name__ == "__main__":
    unittest.main()
