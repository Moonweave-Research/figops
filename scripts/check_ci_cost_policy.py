from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import yaml

WorkflowNode: TypeAlias = None | bool | int | float | str | list["WorkflowNode"] | dict["WorkflowKey", "WorkflowNode"]
WorkflowKey: TypeAlias = str | bool | int | float | None
DOCS_ONLY_PATTERNS = frozenset(("docs/**", "**/*.md", ".omo/**"))
NEGATED_DOCS_ONLY_PATTERNS = frozenset(f"!{pattern}" for pattern in DOCS_ONLY_PATTERNS)
HEAVY_JOB_WORDS = ("heavy", "full", "evidence", "dogfood")


@dataclass(frozen=True, slots=True)
class PolicyCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class WorkflowPolicyReport:
    workflow: Path
    checks: tuple[PolicyCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def _read_workflow(path: Path) -> tuple[WorkflowNode | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"ERROR: cannot read workflow {path}: {exc}"
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"ERROR: cannot parse workflow YAML {path}: {exc}"
    if not isinstance(payload, dict):
        return None, f"ERROR: workflow {path} must be a YAML mapping"
    return payload, None


def _mapping_get(mapping: dict[WorkflowKey, WorkflowNode], key: WorkflowKey) -> WorkflowNode | None:
    return mapping.get(key)


def _string_contains(node: WorkflowNode, needles: tuple[str, ...]) -> bool:
    if isinstance(node, str):
        lowered = node.lower()
        return any(needle in lowered for needle in needles)
    if isinstance(node, list):
        return any(_string_contains(item, needles) for item in node)
    if isinstance(node, dict):
        return any(_string_contains(key, needles) or _string_contains(value, needles) for key, value in node.items())
    return False


def _string_values(node: WorkflowNode) -> tuple[str, ...]:
    if isinstance(node, str):
        return (node,)
    if isinstance(node, list):
        values: list[str] = []
        for item in node:
            values.extend(_string_values(item))
        return tuple(values)
    return ()


def _as_mapping(node: WorkflowNode | None) -> dict[WorkflowKey, WorkflowNode] | None:
    return node if isinstance(node, dict) else None


def _jobs(workflow: dict[WorkflowKey, WorkflowNode]) -> dict[WorkflowKey, WorkflowNode]:
    jobs = _as_mapping(_mapping_get(workflow, "jobs"))
    return jobs if jobs is not None else {}


def _triggers(workflow: dict[WorkflowKey, WorkflowNode]) -> WorkflowNode | None:
    github_on = _mapping_get(workflow, "on")
    if github_on is not None:
        return github_on
    return _mapping_get(workflow, True)


def _has_positive_timeout(node: WorkflowNode | None) -> bool:
    if isinstance(node, int):
        return node > 0
    if isinstance(node, str):
        return node.isdecimal() and int(node) > 0
    return False


def _has_timeout_control(workflow: dict[WorkflowKey, WorkflowNode]) -> PolicyCheck:
    if _has_positive_timeout(_mapping_get(workflow, "timeout-minutes")):
        return PolicyCheck("timeout-minutes", True, "workflow-level timeout-minutes is present")
    jobs = _jobs(workflow)
    if not jobs:
        return PolicyCheck("timeout-minutes", False, "missing jobs; cannot prove timeout-minutes")
    missing = [
        str(job_id)
        for job_id, job in jobs.items()
        if not _has_positive_timeout(_mapping_get(job, "timeout-minutes") if isinstance(job, dict) else None)
    ]
    if missing:
        return PolicyCheck("timeout-minutes", False, f"missing timeout-minutes on jobs: {', '.join(missing)}")
    return PolicyCheck("timeout-minutes", True, "all jobs declare timeout-minutes")


def _has_concurrency_control(workflow: dict[WorkflowKey, WorkflowNode]) -> PolicyCheck:
    if _mapping_get(workflow, "concurrency") is not None:
        return PolicyCheck("concurrency", True, "workflow-level concurrency is present")
    jobs = _jobs(workflow)
    jobs_without_concurrency = [
        str(job_id)
        for job_id, job in jobs.items()
        if not isinstance(job, dict) or _mapping_get(job, "concurrency") is None
    ]
    if jobs and not jobs_without_concurrency:
        return PolicyCheck("concurrency", True, "all jobs declare concurrency")
    return PolicyCheck("concurrency", False, "missing workflow-level concurrency or per-job concurrency")


def _path_policy_covers_docs_only(event: WorkflowNode) -> bool:
    if not isinstance(event, dict):
        return False
    ignored_patterns = {value.strip() for value in _string_values(_mapping_get(event, "paths-ignore"))}
    if ignored_patterns == DOCS_ONLY_PATTERNS:
        return True
    included_patterns = {value.strip() for value in _string_values(_mapping_get(event, "paths"))}
    return included_patterns == NEGATED_DOCS_ONLY_PATTERNS


def _has_trigger_docs_only_policy(triggers: WorkflowNode | None) -> bool:
    if isinstance(triggers, dict):
        return any(_path_policy_covers_docs_only(event) for event in triggers.values())
    return False


def _job_declares_paths_filter(job: dict[WorkflowKey, WorkflowNode]) -> bool:
    identity = f"{_mapping_get(job, 'name')}"
    return "path" in identity.lower() and _string_contains(job, ("paths-filter", "dorny/paths-filter"))


def _path_filter_covers_docs_only(job: dict[WorkflowKey, WorkflowNode]) -> bool:
    return all(_string_contains(job, (pattern,)) for pattern in DOCS_ONLY_PATTERNS)


def _job_if_gates_on_path_filter(job: dict[WorkflowKey, WorkflowNode]) -> bool:
    job_if = _mapping_get(job, "if")
    return _string_contains(job_if, ("needs.", ".outputs.", "docs_only", "docs-only", "non_docs", "non-docs"))


def _job_looks_like_full_suite(job_id: WorkflowKey, job: dict[WorkflowKey, WorkflowNode]) -> bool:
    identity = f"{job_id} {_mapping_get(job, 'name')}"
    return _string_contains(identity, ("test", "full", "suite", "gate")) or _string_contains(
        _mapping_get(job, "steps"),
        ("pytest", "ruff", "tox", "nox"),
    )


def _has_path_filter_job(workflow: dict[WorkflowKey, WorkflowNode]) -> bool:
    jobs = _jobs(workflow)
    has_filter = False
    has_guarded_full_suite = False
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if _job_declares_paths_filter(job) and _path_filter_covers_docs_only(job):
            has_filter = True
        if _job_looks_like_full_suite(job_id, job) and _job_if_gates_on_path_filter(job):
            has_guarded_full_suite = True
    return has_filter and has_guarded_full_suite


def _has_docs_only_avoidance(workflow: dict[WorkflowKey, WorkflowNode]) -> PolicyCheck:
    if _has_trigger_docs_only_policy(_triggers(workflow)):
        return PolicyCheck("docs-only avoidance", True, "docs/**, **/*.md, and .omo/** path policy is present")
    if _has_path_filter_job(workflow):
        return PolicyCheck("docs-only avoidance", True, "path-filter job gates the full test job")
    return PolicyCheck(
        "docs-only avoidance",
        False,
        "missing docs/**, **/*.md, and .omo/** paths policy or explicit path-filter gate for full-suite jobs",
    )


def _workflow_dispatch_inputs(triggers: WorkflowNode | None) -> set[str]:
    if not isinstance(triggers, dict):
        return set()
    workflow_dispatch = _mapping_get(triggers, "workflow_dispatch")
    if not isinstance(workflow_dispatch, dict):
        return set()
    inputs = _mapping_get(workflow_dispatch, "inputs")
    if not isinstance(inputs, dict):
        return set()
    return {str(input_name) for input_name in inputs}


def _is_heavy_job(job_id: WorkflowKey, job: dict[WorkflowKey, WorkflowNode]) -> bool:
    identity = f"{job_id} {_mapping_get(job, 'name')}"
    return _string_contains(identity, HEAVY_JOB_WORDS) or _string_contains(_mapping_get(job, "steps"), HEAVY_JOB_WORDS)


def _job_if_uses_workflow_dispatch_input(job: dict[WorkflowKey, WorkflowNode], dispatch_inputs: set[str]) -> bool:
    job_if = _mapping_get(job, "if")
    if not isinstance(job_if, str):
        return False
    lowered = job_if.lower()
    if "||" in lowered or "&&" not in lowered:
        return False
    if "workflow_dispatch" not in lowered:
        return False
    return any(f"inputs.{input_name}".lower() in lowered for input_name in dispatch_inputs)


def _has_heavy_gate_opt_in(workflow: dict[WorkflowKey, WorkflowNode]) -> PolicyCheck:
    triggers = _triggers(workflow)
    dispatch_inputs = _workflow_dispatch_inputs(triggers)
    if not dispatch_inputs:
        return PolicyCheck("manual heavy gates", False, "missing workflow_dispatch input for opt-in heavy gates")
    heavy_jobs = [
        str(job_id)
        for job_id, job in _jobs(workflow).items()
        if isinstance(job, dict) and _is_heavy_job(job_id, job)
    ]
    if not heavy_jobs:
        return PolicyCheck("manual heavy gates", False, "missing heavy/full/evidence job")
    ungated = [
        str(job_id)
        for job_id, job in _jobs(workflow).items()
        if isinstance(job, dict) and _is_heavy_job(job_id, job) and not _job_if_uses_workflow_dispatch_input(job, dispatch_inputs)
    ]
    if ungated:
        return PolicyCheck(
            "manual heavy gates",
            False,
            f"heavy/full/evidence jobs lack workflow_dispatch input gate: {', '.join(ungated)}",
        )
    return PolicyCheck("manual heavy gates", True, "heavy/full/evidence jobs require workflow_dispatch input gates")


def check_workflow_policy(path: Path) -> WorkflowPolicyReport | str:
    workflow, error = _read_workflow(path)
    if error is not None:
        return error
    if not isinstance(workflow, dict):
        return f"ERROR: workflow {path} must be a YAML mapping"
    return WorkflowPolicyReport(
        workflow=path,
        checks=(
            _has_timeout_control(workflow),
            _has_concurrency_control(workflow),
            _has_docs_only_avoidance(workflow),
            _has_heavy_gate_opt_in(workflow),
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate local CI cost-control policy controls in a workflow YAML file.")
    parser.add_argument("--workflow", required=True, type=Path, help="Workflow YAML file to inspect.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = check_workflow_policy(args.workflow)
    if isinstance(report, str):
        print(report, file=sys.stderr)
        return 2
    print(f"CI cost policy check: {report.workflow}")
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status}: {check.name}: {check.detail}")
    if report.passed:
        print("PASS: required CI cost controls are present.")
        return 0
    print("FAIL: required CI cost controls are missing.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
