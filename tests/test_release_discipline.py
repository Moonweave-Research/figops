import re
import tomllib
from pathlib import Path

from scripts.release_discipline import stale_post_tag_release_blocker

HUB_ROOT = Path(__file__).resolve().parent.parent
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_VERSION_RE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)] - \d{4}-\d{2}-\d{2}$", re.MULTILINE)


def test_package_version_is_semver_and_matches_latest_changelog_entry():
    pyproject = tomllib.loads((HUB_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    changelog = (HUB_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    latest_entry = CHANGELOG_VERSION_RE.search(changelog)

    assert SEMVER_RE.match(version)
    assert latest_entry is not None
    assert latest_entry.group("version") == version


def test_stale_post_tag_release_blocker_requires_new_package_and_changelog_versions():
    blocker = stale_post_tag_release_blocker(
        package_version="0.16.1",
        changelog_version="0.16.1",
        tag_version="0.16.1",
        commits_since_tag=3,
    )

    assert blocker is not None
    assert "v0.16.1" in blocker


def test_stale_post_tag_release_blocker_allows_bumped_package_and_changelog_versions():
    blocker = stale_post_tag_release_blocker(
        package_version="0.16.2",
        changelog_version="0.16.2",
        tag_version="0.16.1",
        commits_since_tag=3,
    )

    assert blocker is None
