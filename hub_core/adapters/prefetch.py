from __future__ import annotations

from typing import Protocol


class Prefetcher(Protocol):
    def ensure_local(self, paths: list[str]) -> None: ...


class NoopPrefetcher:
    def ensure_local(self, paths: list[str]) -> None:
        return None


class GDrivePrefetcher:
    def ensure_local(self, paths: list[str]) -> None:
        from hub_core.utils import ensure_local_files

        ensure_local_files(paths)
