import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import orchestrator


class OrchestratorFailureStageTest(unittest.TestCase):
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
