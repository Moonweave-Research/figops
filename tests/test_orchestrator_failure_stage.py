import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import orchestrator
from hub_core.adapters import LegacyAthenaBridge


class OrchestratorSubprocessTimeoutTest(unittest.TestCase):
    def test_athena_health_hook_timeout_is_swallowed(self):
        # TimeoutExpired must not propagate — the function should return silently.
        with (
            patch(
                "hub_core.adapters.athena.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="athena_health.py", timeout=60),
            ),
        ):
            # Should complete without raising.
            LegacyAthenaBridge().run_health_hook("/fake/root", "/fake/hub")

    def test_draft_bridge_timeout_is_swallowed(self):
        # TimeoutExpired on the draft bridge must not propagate out of main().
        with tempfile.TemporaryDirectory(prefix="hub_bridge_timeout_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()

            config = {
                "project": {"name": "timeout-demo"},
                "execution": {},
                "environment": {"adapters": {"athena": "legacy"}},
            }

            argv = ["orchestrator.py", "--project", str(project_dir), "--step", "plot"]

            bridge_script = Path(tmpdir) / "graph_hub_draft_bridge.py"
            bridge_script.touch()

            def fake_subprocess_run(*_args, **_kwargs):
                raise subprocess.TimeoutExpired(cmd="graph_hub_draft_bridge.py", timeout=60)

            mock_log = MagicMock(return_value=(str(project_dir / "log.jsonl"), {}))

            with (
                # main() does os.environ.setdefault(RESEARCH_HUB_PATH/PROJECT_ROOT, <temp dir>);
                # sandbox the process env so the dead temp-dir path does not leak to later tests.
                patch.dict(os.environ, {}, clear=False),
                patch.object(sys, "argv", argv),
                patch("orchestrator.run_preflight_check"),
                patch(
                    "orchestrator.load_config",
                    return_value=(config, str(project_dir / "project_config.yaml"), "cfg-hash"),
                ),
                patch(
                    "orchestrator.validate_environment_locks",
                    return_value={"ok": True, "strict": False, "python_lock": {}, "r_lock": {}},
                ),
                patch("orchestrator.load_build_state", return_value=({}, str(project_dir / ".build_state.json"))),
                patch("orchestrator.print_provenance"),
                patch("orchestrator.run_plots", return_value=True),
                patch("orchestrator.write_execution_log", side_effect=mock_log),
                patch("orchestrator.get_hub_path", return_value=str(tmpdir)),
                patch("hub_core.adapters.athena.subprocess.run", side_effect=fake_subprocess_run),
            ):
                rc = orchestrator.main()

        # Pipeline itself succeeded; timeout on bridge must not flip the exit code.
        self.assertEqual(rc, 0)


class OrchestratorFailureStageTest(unittest.TestCase):
    def test_list_projects_bypasses_runtime_preflight(self):
        argv = ["orchestrator.py", "--list-projects", "--scan-depth", "2"]

        with (
            patch.object(sys, "argv", argv),
            patch("orchestrator.run_preflight_check", side_effect=AssertionError("preflight should not run")),
            patch("orchestrator.list_projects") as mock_list_projects,
        ):
            rc = orchestrator.main()

        self.assertEqual(rc, 0)
        mock_list_projects.assert_called_once()
        self.assertEqual(mock_list_projects.call_args.kwargs["max_depth"], 2)

    def test_sweep_failure_context_is_logged_as_validate(self):
        with tempfile.TemporaryDirectory(prefix="hub_orch_stage_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            captured = {}

            config = {
                "project": {"name": "failure-stage-demo"},
                "execution": {},
                "sweep": {
                    "enabled": True,
                    "parameter": "lr",
                    "values": [0.01],
                },
            }

            def fake_run_sweep(*_args, **kwargs):
                kwargs["failure_context"]["stage"] = "VALIDATE"
                kwargs["failure_context"]["message"] = "Sweep preflight failed for run 1/1 (lr=0.01)."
                return False

            def fake_write_execution_log(*_args, **kwargs):
                captured["failure_stage"] = kwargs["failure_stage"]
                captured["message"] = kwargs["message"]
                return ("/tmp/fake-log.jsonl", {"failure_stage": kwargs["failure_stage"]})

            argv = [
                "orchestrator.py",
                "--project",
                str(project_dir),
                "--step",
                "plot",
                "--sweep",
            ]

            with (
                patch.object(sys, "argv", argv),
                patch("orchestrator.run_preflight_check"),
                patch(
                    "orchestrator.load_config",
                    return_value=(config, str(project_dir / "project_config.yaml"), "cfg-hash"),
                ),
                patch(
                    "orchestrator.validate_environment_locks",
                    return_value={"ok": True, "strict": False, "python_lock": {}, "r_lock": {}},
                ),
                patch("orchestrator.load_build_state", return_value=({}, str(project_dir / ".build_state.json"))),
                patch("orchestrator.print_provenance"),
                patch("orchestrator.parse_sweep_config", return_value={"runs": [{"lr": "0.01"}]}),
                patch("orchestrator.run_sweep", side_effect=fake_run_sweep),
                patch("orchestrator.write_execution_log", side_effect=fake_write_execution_log),
                patch("orchestrator.dump_pipeline_failure", return_value=str(project_dir / "failure.json")),
            ):
                rc = orchestrator.main()

        self.assertEqual(rc, 1)
        self.assertEqual(captured["failure_stage"], "VALIDATE")
        self.assertIn("Sweep preflight failed", captured["message"])


if __name__ == "__main__":
    unittest.main()
