import re
import tomllib
from pathlib import Path

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
