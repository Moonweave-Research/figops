from __future__ import annotations

import sys
from types import SimpleNamespace

from hub_core import posix_worker_limits


def test_darwin_skips_rlimit_as_but_keeps_cpu_and_file_limits(monkeypatch) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    resource = SimpleNamespace(
        RLIMIT_AS=1,
        RLIMIT_CPU=2,
        RLIMIT_FSIZE=3,
        setrlimit=lambda kind, value: calls.append((kind, value)),
    )
    monkeypatch.setitem(sys.modules, "resource", resource)
    monkeypatch.setattr(posix_worker_limits.sys, "platform", "darwin")

    callback, memory_enforced = posix_worker_limits.build_posix_limit_callback(
        memory_bytes=256,
        cpu_seconds=4.2,
        file_bytes=1024,
    )
    callback()

    assert memory_enforced is False
    assert calls == [(resource.RLIMIT_CPU, (5, 5)), (resource.RLIMIT_FSIZE, (1024, 1024))]


def test_linux_keeps_rlimit_as_cpu_and_file_limits(monkeypatch) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    resource = SimpleNamespace(
        RLIMIT_AS=1,
        RLIMIT_CPU=2,
        RLIMIT_FSIZE=3,
        setrlimit=lambda kind, value: calls.append((kind, value)),
    )
    monkeypatch.setitem(sys.modules, "resource", resource)
    monkeypatch.setattr(posix_worker_limits.sys, "platform", "linux")

    callback, memory_enforced = posix_worker_limits.build_posix_limit_callback(
        memory_bytes=256,
        cpu_seconds=4.2,
        file_bytes=1024,
    )
    callback()

    assert memory_enforced is True
    assert calls == [
        (resource.RLIMIT_AS, (256, 256)),
        (resource.RLIMIT_CPU, (5, 5)),
        (resource.RLIMIT_FSIZE, (1024, 1024)),
    ]
