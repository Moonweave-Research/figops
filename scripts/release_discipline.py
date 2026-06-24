from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_VERSION_RE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)] - \d{4}-\d{2}-\d{2}$", re.MULTILINE)


def _semver_key(version: str | None) -> tuple[int, int, int] | None:
    if version is None:
        return None
    match = SEMVER_RE.match(version)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def stale_post_tag_release_blocker(
    *,
    package_version: str | None,
    changelog_version: str | None,
    tag_version: str,
    commits_since_tag: int,
) -> str | None:
    if commits_since_tag <= 0:
        return None
    tag_key = _semver_key(tag_version)
    package_key = _semver_key(package_version)
    changelog_key = _semver_key(changelog_version)
    if tag_key is None:
        return None
    stale_package = package_key is None or package_key <= tag_key
    stale_changelog = changelog_key is None or changelog_key <= tag_key
    if not stale_package and not stale_changelog:
        return None
    return (
        f"Release metadata is stale: {commits_since_tag} commits after v{tag_version}, "
        f"but pyproject version is {package_version!r} and latest changelog version is {changelog_version!r}. "
        "Bump both before running the public release gate."
    )


def _read_package_version(root: Path) -> str | None:
    pyproject_path = root / "pyproject.toml"
    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = payload.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    return version if isinstance(version, str) else None


def _read_latest_changelog_version(root: Path) -> str | None:
    try:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return None
    match = CHANGELOG_VERSION_RE.search(changelog)
    return match.group("version") if match else None


def _git_stdout(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _latest_release_tag(root: Path) -> str | None:
    return _git_stdout(root, ["describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*"])


def _commits_since_tag(root: Path, tag: str) -> int | None:
    output = _git_stdout(root, ["rev-list", "--count", f"{tag}..HEAD"])
    if output is None:
        return None
    try:
        return int(output)
    except ValueError:
        return None


def post_tag_release_blocker(root: Path) -> str | None:
    tag = _latest_release_tag(root)
    if tag is None or not tag.startswith("v"):
        return None
    commits_since_tag = _commits_since_tag(root, tag)
    if commits_since_tag is None:
        return None
    return stale_post_tag_release_blocker(
        package_version=_read_package_version(root),
        changelog_version=_read_latest_changelog_version(root),
        tag_version=tag.removeprefix("v"),
        commits_since_tag=commits_since_tag,
    )
