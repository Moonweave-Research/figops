from __future__ import annotations

import ast
import errno
from pathlib import Path
from typing import Final
from unittest.mock import patch

import pytest

from tests._symlink import symlink_or_skip

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
WINDOWS_SECURITY_MANIFEST: Final[Path] = REPO_ROOT / ".github" / "windows-security-pytest.txt"
WINDOWS_SECURITY_WORKFLOW: Final[Path] = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_symlink_or_skip_skips_permission_failure_when_strict_mode_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("FIGOPS_REQUIRE_SYMLINK_TESTS", raising=False)
    unavailable = PermissionError(errno.EPERM, "symlink privilege unavailable")

    with (
        patch.object(Path, "symlink_to", side_effect=unavailable),
        pytest.raises(pytest.skip.Exception, match="symlink creation unavailable"),
    ):
        symlink_or_skip(tmp_path / "link", tmp_path / "target")


@pytest.mark.parametrize(
    "unavailable",
    [
        PermissionError(errno.EACCES, "symlink privilege unavailable"),
        NotImplementedError("symlinks are unsupported"),
    ],
)
def test_symlink_or_skip_fails_permission_failure_when_strict_mode_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    unavailable: OSError | NotImplementedError,
) -> None:
    monkeypatch.setenv("FIGOPS_REQUIRE_SYMLINK_TESTS", "1")

    with (
        patch.object(Path, "symlink_to", side_effect=unavailable),
        patch("tests._symlink.pytest.skip"),
        pytest.raises(pytest.fail.Exception, match="required symlink creation unavailable"),
    ):
        symlink_or_skip(tmp_path / "link", tmp_path / "target")


def test_symlink_or_skip_reraises_unrelated_os_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("FIGOPS_REQUIRE_SYMLINK_TESTS", raising=False)
    unexpected = OSError(errno.ENOSPC, "disk full")

    with (
        patch.object(Path, "symlink_to", side_effect=unexpected),
        pytest.raises(OSError, match="disk full"),
    ):
        symlink_or_skip(tmp_path / "link", tmp_path / "target")


def test_windows_security_manifest_includes_every_shared_symlink_caller() -> None:
    caller_node_ids: set[str] = set()
    for test_path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        if test_path == Path(__file__).resolve():
            continue
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for test_node in ast.walk(tree):
            test_name = getattr(test_node, "name", None)
            if not isinstance(test_name, str) or not test_name.startswith("test_"):
                continue
            calls_symlink_helper = any(
                getattr(getattr(candidate, "func", None), "id", None) == "symlink_or_skip"
                for candidate in ast.walk(test_node)
            )
            if not calls_symlink_helper:
                continue
            class_name: str | None = None
            ancestor = parents.get(test_node)
            while ancestor is not None:
                if type(ancestor) is ast.ClassDef:
                    class_name = ancestor.name
                    break
                ancestor = parents.get(ancestor)
            relative_path = test_path.relative_to(REPO_ROOT).as_posix()
            node_id = f"{relative_path}::{class_name}::{test_name}" if class_name else f"{relative_path}::{test_name}"
            caller_node_ids.add(node_id)

    assert len(caller_node_ids) == 26
    assert WINDOWS_SECURITY_MANIFEST.is_file()
    selected_node_ids = {
        line.strip()
        for line in WINDOWS_SECURITY_MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert sorted(caller_node_ids - selected_node_ids) == []
    workflow = WINDOWS_SECURITY_WORKFLOW.read_text(encoding="utf-8")
    assert '"@.github/windows-security-pytest.txt"' in workflow
    assert '-k "symlink' not in workflow
