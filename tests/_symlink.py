from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Final, NoReturn

import pytest

REQUIRE_SYMLINK_TESTS_ENV: Final[str] = "FIGOPS_REQUIRE_SYMLINK_TESTS"


def _handle_unavailable_symlink(exc: OSError | NotImplementedError) -> NoReturn:
    message = f"symlink creation unavailable: {exc}"
    if os.environ.get(REQUIRE_SYMLINK_TESTS_ENV) == "1":
        pytest.fail(f"required {message}")
    pytest.skip(message)


def symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except NotImplementedError as exc:
        _handle_unavailable_symlink(exc)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314 or exc.errno in {errno.EACCES, errno.EPERM}:
            _handle_unavailable_symlink(exc)
        raise
