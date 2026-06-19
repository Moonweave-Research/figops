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


class NullAthena:
    def run_health_hook(self, root_dir: str, hub_path: str) -> None:
        return None

    def run_draft_bridge(self, project_dir: str, hub_path: str) -> None:
        return None


class LegacyAthenaBridge:
    def run_health_hook(self, root_dir: str, hub_path: str) -> None:
        from orchestrator import run_athena_health_hook

        run_athena_health_hook(root_dir, hub_path)

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
