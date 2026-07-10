from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
import yaml

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
WORKFLOW_DIR: Final[Path] = REPO_ROOT / ".github" / "workflows"
WORKFLOW_PATHS: Final[tuple[Path, ...]] = tuple(sorted(WORKFLOW_DIR.glob("*.y*ml")))
DEPENDABOT_PATH: Final[Path] = REPO_ROOT / ".github" / "dependabot.yml"
ACTION_REFS: Final[dict[str, tuple[str, str]]] = {
    "actions/checkout": ("34e114876b0b11c390a56381ad16ebd13914f8d5", "v4"),
    "actions/download-artifact": ("d3f86a106a0bac45b974a628896c90dbdf5c8093", "v4"),
    "actions/upload-artifact": ("ea165f8d65b6e75b540449e92b4886f43607fa02", "v4"),
    "astral-sh/setup-uv": ("d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86", "v5"),
    "pypa/gh-action-pypi-publish": ("cef221092ed1bacb1cc03d23a2d87d1d172e277b", "release/v1"),
    "r-lib/actions/setup-r": ("d3c5be51b12e724e68f33216ca3c148b66d5f0b6", "v2"),
}
OIDC_PUBLISH_JOBS: Final[frozenset[str]] = frozenset({"publish-pypi", "publish-testpypi"})
USES_LINE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<uses>\S+)(?:\s+#\s*(?P<comment>\S+))?\s*$")


def _permission_errors(permissions, *, owner: str, allow_oidc: bool = False) -> list[str]:
    if permissions is None:
        return []
    if permissions == "write-all":
        return [f"{owner} grants write-all"]
    if not isinstance(permissions, dict):
        return []

    errors: list[str] = []
    for scope, access in permissions.items():
        if access != "write":
            continue
        if scope == "id-token" and allow_oidc:
            continue
        errors.append(f"{owner} grants {scope}: write")
    return errors


def _workflow_policy_errors(workflow_text: str, *, workflow_name: str) -> list[str]:
    document = yaml.load(workflow_text, Loader=yaml.BaseLoader)
    if not isinstance(document, dict):
        return ["workflow root is not a mapping"]

    errors: list[str] = []
    triggers = document.get("on")
    if isinstance(triggers, dict) and "pull_request_target" in triggers:
        errors.append("pull_request_target is forbidden")
    permissions = document.get("permissions")
    if permissions != {"contents": "read"}:
        errors.append("workflow permissions must be contents: read")
    errors.extend(_permission_errors(permissions, owner="workflow"))

    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return [*errors, "jobs is not a mapping"]
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        allow_oidc = workflow_name == "publish.yml" and job_name in OIDC_PUBLISH_JOBS
        errors.extend(_permission_errors(job.get("permissions"), owner=job_name, allow_oidc=allow_oidc))
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if not isinstance(uses, str) or uses.startswith("./"):
                continue
            action, separator, ref = uses.partition("@")
            expected = ACTION_REFS.get(action)
            if separator != "@" or expected is None or ref != expected[0]:
                errors.append(f"unapproved or mutable action reference: {uses}")

    for line in workflow_text.splitlines():
        match = USES_LINE.match(line)
        if match is None:
            continue
        uses = match.group("uses")
        if uses.startswith("./"):
            continue
        action, separator, ref = uses.partition("@")
        expected = ACTION_REFS.get(action)
        if separator == "@" and expected is not None and ref == expected[0] and match.group("comment") != expected[1]:
            errors.append(f"missing version comment for {uses}")
    return errors


@pytest.mark.parametrize("workflow_path", WORKFLOW_PATHS, ids=lambda path: path.name)
def test_workflows_use_only_pinned_actions_and_narrow_permissions(workflow_path: Path) -> None:
    errors = _workflow_policy_errors(workflow_path.read_text(encoding="utf-8"), workflow_name=workflow_path.name)

    assert errors == []


def test_approved_action_refs_are_exact_lowercase_commit_shas() -> None:
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref, _comment in ACTION_REFS.values())


def test_workflow_policy_rejects_mutable_action_tag() -> None:
    workflow = """
on: push
permissions:
  contents: read
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
"""

    assert _workflow_policy_errors(workflow, workflow_name="fixture.yml") == [
        "unapproved or mutable action reference: actions/checkout@v4"
    ]


def test_workflow_policy_rejects_broad_write_permission() -> None:
    workflow = """
on: push
permissions:
  contents: write
jobs:
  test:
    steps: []
"""

    assert _workflow_policy_errors(workflow, workflow_name="fixture.yml") == [
        "workflow permissions must be contents: read",
        "workflow grants contents: write",
    ]


def test_workflow_policy_rejects_oidc_outside_publish_workflow() -> None:
    workflow = """
on: push
permissions:
  contents: read
jobs:
  publish-pypi:
    permissions:
      id-token: write
    steps: []
"""

    assert _workflow_policy_errors(workflow, workflow_name="fixture.yml") == ["publish-pypi grants id-token: write"]


def test_windows_security_job_is_strict_and_locked() -> None:
    document = yaml.load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    jobs = document["jobs"]
    windows_security = jobs["windows-security"]
    assert windows_security["runs-on"] == "windows-latest"
    assert windows_security["env"]["FIGOPS_REQUIRE_SYMLINK_TESTS"] == "1"
    steps = windows_security["steps"]
    setup_uv = next(step for step in steps if step.get("name") == "Install locked uv")
    assert setup_uv["with"]["python-version"] == "3.12"
    assert setup_uv["with"]["version"] == "0.11.25"
    sync = next(step for step in steps if step.get("name") == "Sync locked dependencies")
    assert sync["run"] == "uv sync --locked --all-extras --group dev"
    security_test = next(step for step in steps if step.get("name") == "Run Windows security tests")
    assert "uv run --locked" in security_test["run"]
    assert "--junitxml=windows-security-junit.xml" in security_test["run"]
    assert '"@.github/windows-security-pytest.txt"' in security_test["run"]
    skip_gate = next(step for step in steps if step.get("name") == "Require zero skipped security tests")
    assert 'SelectNodes("//testcase/skipped")' in skip_gate["run"]


def test_dependabot_updates_github_actions_weekly() -> None:
    document = yaml.load(DEPENDABOT_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    updates = document.get("updates")
    assert isinstance(updates, list)
    github_actions = [entry for entry in updates if entry.get("package-ecosystem") == "github-actions"]
    assert len(github_actions) == 1
    assert github_actions[0]["directory"] == "/"
    assert github_actions[0]["schedule"]["interval"] == "weekly"
