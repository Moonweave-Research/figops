import re
import tomllib
from pathlib import Path

from scripts.release_discipline import post_tag_release_blocker, stale_post_tag_release_blocker

HUB_ROOT = Path(__file__).resolve().parent.parent
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_VERSION_RE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)] - \d{4}-\d{2}-\d{2}$", re.MULTILINE)
POST_TAG_METADATA_ROW = "| post_tag_metadata | 1 | requires_release_decision | yes |"


def _assert_release_status_matches_post_tag_state(status: str, post_tag_blocker: str | None) -> None:
    status_is_blocked = "- Technical release gate: blocked" in status
    status_is_green = "- Technical release gate: ok" in status

    assert status_is_blocked != status_is_green
    if status_is_green:
        assert post_tag_blocker is None
        assert "- Technical release gate: ok" in status
        assert "- Repository technically eligible for public release: yes" in status
        assert "- Repository release allowed: yes" in status
        assert "post_tag_metadata" not in status
        return

    assert "- Technical release gate: blocked" in status
    assert "- Repository technically eligible for public release: no" in status
    assert "- Repository release allowed: no" in status
    assert "- Technical blockers:" in status
    assert "- Technical blockers: 0" not in status
    assert POST_TAG_METADATA_ROW in status
    if post_tag_blocker is not None:
        assert "Release metadata is stale" in post_tag_blocker


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


def test_release_status_assertion_preserves_clean_gate_expectations():
    status = """
- Repository technically eligible for public release: yes
- Repository release allowed: yes
- Technical release gate: ok
"""

    _assert_release_status_matches_post_tag_state(status, None)


def test_release_status_assertion_fails_closed_for_stale_post_tag_metadata():
    status = f"""
- Repository technically eligible for public release: no
- Repository release allowed: no
- Technical release gate: blocked
- Technical blockers: 1
{POST_TAG_METADATA_ROW}
"""

    _assert_release_status_matches_post_tag_state(status, "Release metadata is stale: 3 commits after v0.20.0")


def test_v020_release_requires_structure_p1_gate():
    status = (HUB_ROOT / "docs" / "packaging" / "public-release-status.md").read_text(
        encoding="utf-8"
    )
    decision = (
        HUB_ROOT / "docs" / "packaging" / "public-release-decision-record.md"
    ).read_text(encoding="utf-8")
    structure_ssot = (
        HUB_ROOT
        / "docs"
        / "specs"
        / "2026-07-15-project-structure-runtime-integrity-plan.md"
    ).read_text(encoding="utf-8")

    # A green technical inventory remains necessary; owner-recorded evidence
    # supplies release authority for this scoped version. Post-tag metadata
    # drift must fail closed until the next release version is chosen.
    _assert_release_status_matches_post_tag_state(status, post_tag_release_blocker(HUB_ROOT))

    assert "- Repository publication authorized: yes" in status
    assert "- Authorization evidence references: 1" in status
    assert "technical gate remains independent evidence" in status
    assert "Decision record:" in status
    assert "PR #224 owner authorization" in decision
    assert "required human, legal, and release approvals granted" in decision
    assert "| TBD |" not in decision
    assert "must not be presented as released merely because tests or" in structure_ssot
    assert "all repository-required approvals must be recorded" in structure_ssot
