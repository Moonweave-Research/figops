from __future__ import annotations

import os
import time
from typing import Protocol

from hub_core.logging import get_logger
from hub_core.utils import expand_declared_paths

logger = get_logger(__name__)
PREFETCH_ATTEMPTS = 3
PREFETCH_RETRY_DELAYS = (0.25, 1.0)


class Prefetcher(Protocol):
    def ensure_local(self, paths: list[str]) -> None: ...


class NoopPrefetcher:
    def ensure_local(self, paths: list[str]) -> None:
        return None


class GDrivePrefetcher:
    def ensure_local(self, paths: list[str]) -> None:
        ensure_local_files(paths)


def ensure_local_files(paths):
    if not paths:
        return

    targets = []
    for path in expand_declared_paths(os.getcwd(), paths):
        if os.path.isfile(path):
            targets.append(path)
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for filename in files:
                    targets.append(os.path.join(root, filename))

    total = len(targets)
    if total == 0:
        return

    logger.info("   [Prefetch] Ensuring %s files are local (Google Drive Sync)...", total)
    success_count = 0
    fail_count = 0
    failed_targets = []

    for index, path in enumerate(targets, 1):
        filename = os.path.basename(path)
        display_name = (filename[:30] + "..") if len(filename) > 32 else filename
        logger.debug("      - Progress: [%s/%s] %s", index, total, display_name)

        last_error = None
        attempts_used = 0
        for attempt in range(PREFETCH_ATTEMPTS):
            attempts_used = attempt + 1
            try:
                with open(path, "rb") as handle:
                    handle.read(1)
                success_count += 1
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < len(PREFETCH_RETRY_DELAYS):
                    time.sleep(PREFETCH_RETRY_DELAYS[attempt])

        if last_error is not None:
            fail_count += 1
            failed_targets.append((display_name, type(last_error).__name__, attempts_used))

    if fail_count > 0:
        failed_preview = ", ".join(
            f"{name} ({error_name}, attempts={attempts})"
            for name, error_name, attempts in failed_targets[:3]
        )
        logger.warning(
            "      Prefetch incomplete: %s/%s ready, %s timed out or unavailable.",
            success_count,
            total,
            fail_count,
        )
        if failed_preview:
            logger.warning("         unresolved: %s", failed_preview)
        logger.warning("         pipeline will continue and let the downstream step decide.")
    else:
        logger.info("      All %s files are ready locally.", success_count)
