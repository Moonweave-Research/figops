import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import orchestrator
from hub_core import process_runner


class OrchestratorAdapterSelectionTest(unittest.TestCase):
    def test_default_adapters_skip_athena_hooks_with_zero_bespoke_env(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_orch_adapters_") as tmpdir:
            root_dir = Path(tmpdir)
            project_dir = root_dir / "project"
            project_dir.mkdir()
            (root_dir / "graph_hub_draft_bridge.py").touch()

            config = {"project": {"name": "generic-default"}, "execution": {}}
            argv = ["orchestrator.py", "--project", str(project_dir), "--step", "plot"]
            mock_log = MagicMock(return_value=(str(project_dir / "log.jsonl"), {}))

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", argv),
                patch("orchestrator.get_hub_path", return_value=str(root_dir)),
                patch("orchestrator.get_research_root", return_value=str(root_dir)),
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
                patch("hub_core.provenance._readable_git_commit", return_value="git-hash"),
                patch(
                    "hub_core.adapters.athena.LegacyAthenaBridge.run_health_hook",
                    side_effect=AssertionError("legacy health hook ran"),
                ),
                patch(
                    "hub_core.adapters.athena.LegacyAthenaBridge.run_draft_bridge",
                    side_effect=AssertionError("legacy draft bridge ran"),
                ),
            ):
                rc = orchestrator.main()

        self.assertEqual(rc, 0)

    def test_legacy_athena_adapter_runs_opt_in_hooks(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_orch_adapters_") as tmpdir:
            root_dir = Path(tmpdir)
            project_dir = root_dir / "project"
            project_dir.mkdir()
            (root_dir / "graph_hub_draft_bridge.py").touch()

            config = {
                "project": {"name": "legacy-athena"},
                "execution": {},
                "environment": {"adapters": {"athena": "legacy"}},
            }
            argv = ["orchestrator.py", "--project", str(project_dir), "--step", "plot"]
            mock_log = MagicMock(return_value=(str(project_dir / "log.jsonl"), {}))

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", argv),
                patch("orchestrator.get_hub_path", return_value=str(root_dir)),
                patch("orchestrator.get_research_root", return_value=str(root_dir)),
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
                patch("hub_core.provenance._readable_git_commit", return_value="git-hash"),
                patch("hub_core.adapters.athena.LegacyAthenaBridge.run_health_hook") as health_hook,
                patch("hub_core.adapters.athena.subprocess.run") as draft_run,
            ):
                draft_run.return_value.returncode = 0
                rc = orchestrator.main()

        self.assertEqual(rc, 0)
        health_hook.assert_called_once_with(str(root_dir), str(root_dir))
        draft_run.assert_called_once()


class ProcessRunnerPrefetchAdapterTest(unittest.TestCase):
    def test_analysis_defaults_to_noop_prefetcher(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_prefetch_") as tmpdir:
            project_dir = Path(tmpdir)
            script = project_dir / "analyze.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            input_file = project_dir / "input.csv"
            input_file.write_text("x\n1\n", encoding="utf-8")
            config = {
                "project": {"name": "noop-prefetch"},
                "pipeline": {"analysis": [{"script": "analyze.py", "lang": "python", "inputs": ["input.csv"]}]},
                "language_policy": {"analysis_lang": "python", "allow_nonstandard": True},
            }

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("hub_core.process_runner.run_command", return_value=True),
                patch("hub_core.utils.ensure_local_files", side_effect=AssertionError("gdrive prefetch ran")),
            ):
                result = process_runner.run_analysis(
                    str(project_dir),
                    config,
                    build_state={},
                    build_state_path=str(project_dir / ".build_state.json"),
                    config_hash="cfg-hash",
                    force=True,
                )

        self.assertTrue(result)

    def test_analysis_uses_gdrive_prefetcher_when_opted_in(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_prefetch_") as tmpdir:
            project_dir = Path(tmpdir)
            script = project_dir / "analyze.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            input_file = project_dir / "input.csv"
            input_file.write_text("x\n1\n", encoding="utf-8")
            config = {
                "project": {"name": "gdrive-prefetch"},
                "environment": {"adapters": {"prefetch": "gdrive"}},
                "pipeline": {"analysis": [{"script": "analyze.py", "lang": "python", "inputs": ["input.csv"]}]},
                "language_policy": {"analysis_lang": "python", "allow_nonstandard": True},
            }

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("hub_core.process_runner.run_command", return_value=True),
                patch("hub_core.utils.ensure_local_files") as ensure_local,
            ):
                result = process_runner.run_analysis(
                    str(project_dir),
                    config,
                    build_state={},
                    build_state_path=str(project_dir / ".build_state.json"),
                    config_hash="cfg-hash",
                    force=True,
                )

        self.assertTrue(result)
        ensure_local.assert_called_once_with([str(input_file)])


if __name__ == "__main__":
    unittest.main()
