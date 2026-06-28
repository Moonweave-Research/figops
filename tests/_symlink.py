from __future__ import annotations

import errno
from pathlib import Path

import pytest


def symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except NotImplementedError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314 or exc.errno in {errno.EACCES, errno.EPERM}:
            pytest.skip(f"symlink creation unavailable: {exc}")
        raise
