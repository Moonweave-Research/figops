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
    "r-lib/actions/setup-renv": ("d3c5be51b12e724e68f33216ca3c148b66d5f0b6", "v2"),
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


def test_test_and_ruff_jobs_are_gating_and_locked() -> None:
    document = yaml.load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    jobs = document["jobs"]
    for job_name, execution_step in (("test", "Tests"), ("lint", "Ruff")):
        job = jobs[job_name]
        steps = job["steps"]
        setup_uv = next(step for step in steps if step.get("name") == "Install locked uv")
        assert setup_uv["with"]["python-version"] == "3.12"
        assert setup_uv["with"]["version"] == "0.11.25"
        sync = next(step for step in steps if step.get("name") == "Sync locked dependencies")
        assert sync["run"] == "uv sync --locked --group dev"
        execution = next(step for step in steps if step.get("name") == execution_step)
        assert "uv run --locked" in execution["run"]
        assert "continue-on-error" not in execution

    assert jobs["test"]["name"] == "Test (gating)"
    assert jobs["lint"]["name"] == "Ruff (gating)"


def test_macos_native_alias_smoke_precedes_full_regression_and_cannot_skip() -> None:
    document = yaml.load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    test_job = document["jobs"]["test"]
    assert "if" not in test_job
    assert "continue-on-error" not in test_job
    steps = test_job["steps"]
    step_names = [step.get("name") for step in steps]
    assert step_names == [
        None,
        "Install locked uv",
        "Sync locked dependencies",
        "Run native macOS alias smoke",
        "Require exactly nine native macOS alias passes",
        "Tests",
    ]
    smoke = next(step for step in steps if step.get("name") == "Run native macOS alias smoke")
    assert smoke["run"].split() == [
        "uv",
        "run",
        "--locked",
        "python",
        "-m",
        "pytest",
        "-q",
        "--basetemp=/var/tmp/figops-macos-path-identity-${{",
        "github.run_id",
        "}}-${{",
        "github.run_attempt",
        "}}",
        "--junitxml=macos-path-identity-junit.xml",
        "tests/test_macos_path_identity.py",
        "tests/test_project_config_reader.py::test_absolute_config_accepts_macos_var_alias",
    ]
    count_gate = next(
        step for step in steps if step.get("name") == "Require exactly nine native macOS alias passes"
    )
    assert count_gate["run"].strip() == """\
uv run --locked python - <<'PY'
import xml.etree.ElementTree as ET

root = ET.parse("macos-path-identity-junit.xml").getroot()
suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
counts = {
    key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
passed = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
if passed != 9 or counts["tests"] != 9 or any(counts[key] for key in ("failures", "errors", "skipped")):
    raise SystemExit(f"native macOS alias gate requires 9 passed/0 skipped; observed {counts}, passed={passed}")
PY"""
    assert all("if" not in step and "continue-on-error" not in step for step in steps)
    assert step_names.index("Sync locked dependencies") < step_names.index("Run native macOS alias smoke")
    assert step_names.index("Require exactly nine native macOS alias passes") < step_names.index("Tests")


def _assert_actual_r_job(actual_r: dict) -> None:
    assert actual_r["name"] == "Actual R integration (gating)"
    assert actual_r["runs-on"] == "ubuntu-latest"
    assert "if" not in actual_r
    assert "continue-on-error" not in actual_r
    steps = actual_r["steps"]
    assert [step.get("name") for step in steps] == [
        None,
        "Install locked uv",
        "Sync locked dependencies",
        "Install R",
        "Restore locked R dependencies",
        "Export locked R library",
        "Verify locked R and readr",
        "Run actual R integration tests",
        "Require exactly two passed and zero skipped",
    ]
    assert all("if" not in step and "continue-on-error" not in step for step in steps)

    setup_uv = next(step for step in steps if step.get("name") == "Install locked uv")
    assert setup_uv["with"] == {"python-version": "3.12", "version": "0.11.25"}
    sync = next(step for step in steps if step.get("name") == "Sync locked dependencies")
    assert sync["run"] == "uv sync --locked --group dev"

    setup_r = next(step for step in steps if step.get("name") == "Install R")
    assert setup_r["uses"] == (
        "r-lib/actions/setup-r@d3c5be51b12e724e68f33216ca3c148b66d5f0b6"
    )
    assert setup_r["with"] == {"r-version": "renv"}
    setup_renv = next(step for step in steps if step.get("name") == "Restore locked R dependencies")
    assert setup_renv["uses"] == (
        "r-lib/actions/setup-renv@d3c5be51b12e724e68f33216ca3c148b66d5f0b6"
    )

    export_library = next(step for step in steps if step.get("name") == "Export locked R library")
    export_lines = export_library["run"].splitlines()
    assert export_lines == [
        'locked_r_lib="$(Rscript -e \'cat(normalizePath(.libPaths()[1], winslash = "/", mustWork = TRUE))\')"',
        'existing_r_libs_user="${R_LIBS_USER:-}"',
        (
            'if [[ -z "$locked_r_lib" || "$locked_r_lib" == *$\'\\n\'* || '
            '"$locked_r_lib" == *$\'\\r\'* || "$existing_r_libs_user" == *$\'\\n\'* || '
            '"$existing_r_libs_user" == *$\'\\r\'* ]]; then'
        ),
        '  echo "Refusing unsafe R library path" >&2',
        "  exit 1",
        "fi",
        'r_libs_user="$locked_r_lib"',
        'if [[ -n "$existing_r_libs_user" ]]; then',
        '  r_libs_user="$locked_r_lib:$existing_r_libs_user"',
        "fi",
        'printf \'%s\\n\' "R_LIBS_USER=$r_libs_user" >> "$GITHUB_ENV"',
    ]
    assert 'r_libs_user="$locked_r_lib"' in export_lines
    assert '  r_libs_user="$locked_r_lib:$existing_r_libs_user"' in export_lines
    assert export_lines.index('r_libs_user="$locked_r_lib"') < export_lines.index(
        '  r_libs_user="$locked_r_lib:$existing_r_libs_user"'
    )
    assert 'printf \'%s\\n\' "R_LIBS_USER=$locked_r_lib" >> "$GITHUB_ENV"' not in export_lines

    verify_readr = next(step for step in steps if step.get("name") == "Verify locked R and readr")
    assert verify_readr["run"].splitlines() == [
        'verification_cwd="$(mktemp -d)"',
        'trap \'rm -rf -- "$verification_cwd"\' EXIT',
        'cd "$verification_cwd"',
        (
            'Rscript -e "stopifnot(getRversion() == \'4.4.2\', '
            "packageVersion('readr') == '2.2.0', packageVersion('dplyr') == '1.2.0')\""
        ),
        'Rscript -e "suppressPackageStartupMessages({library(readr); library(dplyr)})"',
    ]
    execution = next(step for step in steps if step.get("name") == "Run actual R integration tests")
    assert execution["run"].split() == [
        "uv",
        "run",
        "--locked",
        "python",
        "-m",
        "pytest",
        "-q",
        "--junitxml=actual-r-junit.xml",
        "tests/test_smoke.py::HubSmokeTest::test_scaffold_all_and_cache",
        "tests/test_process_runner_new.py::TestScaffoldRAnalysisInputContract::test_scaffold_r_analysis_reads_real_data_from_normalized_raw_dir",
    ]
    skip_gate = next(
        step for step in steps if step.get("name") == "Require exactly two passed and zero skipped"
    )
    assert skip_gate["run"].strip() == """\
uv run --locked python - <<'PY'
import xml.etree.ElementTree as ET

root = ET.parse("actual-r-junit.xml").getroot()
suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
counts = {
    key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
passed = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
if passed != 2 or counts["tests"] != 2 or any(counts[key] for key in ("failures", "errors", "skipped")):
    raise SystemExit(f"actual-R gate requires 2 passed/0 skipped; observed {counts}, passed={passed}")
PY"""


@pytest.mark.parametrize("workflow_name", ("ci.yml", "publish.yml"))
def test_actual_r_job_is_gating_locked_and_cannot_silently_skip(workflow_name: str) -> None:
    document = yaml.load((WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    _assert_actual_r_job(document["jobs"]["actual-r"])


def test_publish_cannot_build_or_upload_before_actual_r_gate() -> None:
    document = yaml.load((WORKFLOW_DIR / "publish.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    jobs = document["jobs"]
    assert jobs["actual-r"]["needs"] == "release-ref"
    assert jobs["build"]["needs"] == ["release-ref", "actual-r"]
    assert "if" not in jobs["build"]
    assert "continue-on-error" not in jobs["build"]
    assert jobs["publish-testpypi"]["needs"] == "build"
    assert jobs["publish-pypi"]["needs"] == "build"


def test_publish_build_job_uses_pinned_uv_and_locked_project_commands() -> None:
    document = yaml.load((WORKFLOW_DIR / "publish.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    steps = document["jobs"]["build"]["steps"]
    setup_uv = next(step for step in steps if step.get("name") == "Install locked uv")
    assert setup_uv["with"]["python-version"] == "3.12"
    assert setup_uv["with"]["version"] == "0.11.25"
    sync = next(step for step in steps if step.get("name") == "Sync locked dependencies")
    assert sync["run"] == "uv sync --locked --group dev"

    locked_steps = (
        "Run release-critical tests",
        "Package metadata smoke",
        "Public package surface",
        "Consumer install smoke",
        "Twine metadata check",
        "Guard upload policy",
    )
    for step_name in locked_steps:
        step = next(step for step in steps if step.get("name") == step_name)
        assert "--locked" in step["run"]

    build = next(step for step in steps if step.get("name") == "Build distributions")
    assert build["run"] == "uv build --no-sources"


def test_dependency_audit_is_reproducible_and_remains_advisory() -> None:
    document = yaml.load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    audit = document["jobs"]["audit"]
    assert audit["name"] == "Dependency audit (advisory)"
    assert audit["env"] == {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    steps = audit["steps"]
    setup_uv = next(step for step in steps if step.get("name") == "Install locked uv")
    assert setup_uv["with"]["python-version"] == "3.12"
    assert setup_uv["with"]["version"] == "0.11.25"
    export = next(step for step in steps if step.get("name") == "Export resolved requirements")
    assert export["run"] == "uv export --locked --no-emit-project --no-hashes -o requirements-audit.txt"
    pip_audit = next(step for step in steps if step.get("name") == "pip-audit")
    assert pip_audit["continue-on-error"] == "true"
    assert pip_audit["run"] == (
        "uvx --from pip-audit==2.10.1 pip-audit -r requirements-audit.txt --strict"
    )


def test_dependabot_updates_github_actions_weekly() -> None:
    document = yaml.load(DEPENDABOT_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert isinstance(document, dict)
    updates = document.get("updates")
    assert isinstance(updates, list)
    github_actions = [entry for entry in updates if entry.get("package-ecosystem") == "github-actions"]
    assert len(github_actions) == 1
    assert github_actions[0]["directory"] == "/"
    assert github_actions[0]["schedule"]["interval"] == "weekly"
