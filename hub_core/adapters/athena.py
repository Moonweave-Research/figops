from __future__ import annotations

import os
import subprocess
import sys
from typing import Protocol

from hub_core.logging import get_logger

SUBPROCESS_TIMEOUT = 60
logger = get_logger(__name__)


class AthenaBridge(Protocol):
    def run_health_hook(self, root_dir: str, hub_path: str) -> None: ...

    def run_draft_bridge(self, project_dir: str, hub_path: str) -> None: ...

    def load_solve_context_env(self) -> dict[str, str]: ...

    def load_solve_data_context(self) -> dict: ...


class NullAthena:
    def run_health_hook(self, root_dir: str, hub_path: str) -> None:
        return None

    def run_draft_bridge(self, project_dir: str, hub_path: str) -> None:
        return None

    def load_solve_context_env(self) -> dict[str, str]:
        return {}

    def load_solve_data_context(self) -> dict:
        return {}


class LegacyAthenaBridge:
    _athena_path_registered = False

    def _ensure_athena_on_path(self) -> None:
        if self._athena_path_registered:
            return
        from hub_core.utils import get_hub_path

        athena_root = os.path.abspath(os.path.join(get_hub_path(), "..", "[Athena]"))
        if athena_root not in sys.path:
            sys.path.insert(0, athena_root)
        self._athena_path_registered = True

    def load_solve_context_env(self) -> dict[str, str]:
        try:
            self._ensure_athena_on_path()
            from integrations.solve_live_context import load_as_env_vars

            return load_as_env_vars()
        except Exception as exc:
            logger.warning("      Failed to load solve context env: %s: %s", type(exc).__name__, exc)
            return {}

    def load_solve_data_context(self) -> dict:
        try:
            self._ensure_athena_on_path()
            from integrations.solve_live_context import load_as_data_context

            return load_as_data_context()
        except Exception as exc:
            logger.warning("      Failed to load solve data context: %s: %s", type(exc).__name__, exc)
            return {}

    def run_health_hook(self, root_dir: str, hub_path: str) -> None:
        health_script = os.path.join(root_dir, "scripts", "athena_health.py")
        report_path = os.path.join(root_dir, "workspace_state.md")

        try:
            result = subprocess.run(
                [sys.executable, health_script, "--md-out", report_path],
                capture_output=True,
                text=True,
                cwd=hub_path,
                check=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            logger.warning("\nAthena Health hook timed out; pipeline result is unchanged.")
            return
        except subprocess.CalledProcessError as exc:
            logger.warning("\nAthena Health hook failed; pipeline result is unchanged.")
            stderr_preview = (exc.stderr or exc.stdout or "").strip()
            if stderr_preview:
                logger.warning("   %s", stderr_preview[:200])
            return
        except Exception as exc:
            logger.warning("\nAthena Health hook error: %s; pipeline result is unchanged.", exc)
            return

        if result.returncode == 0:
            logger.info("\nAthena Health: workspace_state.md updated.")
            logger.info("   - sync_status refreshed.")

    def run_draft_bridge(self, project_dir: str, hub_path: str) -> None:
        bridge_script = os.path.join(hub_path, "graph_hub_draft_bridge.py")
        if not os.path.exists(bridge_script):
            return
        try:
            result = subprocess.run(
                [sys.executable, bridge_script, "--project", project_dir, "--manifest-only"],
                capture_output=True,
                text=True,
                cwd=hub_path,
                timeout=SUBPROCESS_TIMEOUT,
            )
            if result.returncode == 0:
                logger.info("\nDraft Bridge: manifest updated.")
                logger.info("   Use /draft show-candidates <alias> to inspect candidates.")
            else:
                logger.warning("\nDraft Bridge failed; pipeline result is unchanged.")
                if result.stderr:
                    logger.warning("   %s", result.stderr.strip()[:200])
        except subprocess.TimeoutExpired:
            logger.warning("\nDraft Bridge timed out; pipeline result is unchanged.")
        except Exception as exc:
            logger.warning("\nDraft Bridge error: %s; pipeline result is unchanged.", exc)
