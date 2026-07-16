"""Portable POSIX worker limits with explicit macOS memory semantics."""

from __future__ import annotations

import math
import sys
from collections.abc import Callable


def build_posix_limit_callback(
    *,
    memory_bytes: int,
    cpu_seconds: float,
    file_bytes: int,
) -> tuple[Callable[[], None], bool]:
    """Return a pre-exec limiter and whether address-space limiting is active.

    ``RLIMIT_AS`` is not a reliable containment primitive on macOS.  Darwin
    workers therefore retain CPU and file-size limits plus process-session
    isolation, while reporting that the hard memory limit is unavailable.
    """

    import resource

    memory_enforced = sys.platform != "darwin" and hasattr(resource, "RLIMIT_AS")
    cpu_limit = max(1, int(math.ceil(cpu_seconds)))

    def apply_limits() -> None:
        if memory_enforced:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))

    return apply_limits, memory_enforced
