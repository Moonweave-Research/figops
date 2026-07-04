# /// script
# requires-python = ">=3.12"
# ///
# --- How to run ---
# python hub_uv.py run python scripts/check_geometry_rubric_map.py

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final, Mapping, assert_never

from hub_core.mcp.render_geometry_schemas import GEOMETRY_METRIC_NAMES

HUB_ROOT: Final = Path(__file__).resolve().parent.parent
MAP_PATH: Final = HUB_ROOT / "docs" / "specs" / "geometry-diagnostic-rubric-map.json"
QA_PATH: Final = HUB_ROOT / "docs" / "QA.md"
RUBRIC_PATH: Final = HUB_ROOT / "docs" / "specs" / "2026-06-30-figure-quality-rubric.md"
DOC_POINTER: Final = "docs/specs/geometry-diagnostic-rubric-map.json"
CHECKER_POINTER: Final = "scripts/check_geometry_rubric_map.py"
HARD_IDS: Final = frozenset({"FQ-H1", "FQ-H2", "FQ-H3", "FQ-H4", "FQ-H5"})
ADVISORY_IDS: Final = frozenset({"FQ-A1", "FQ-A2", "FQ-A3", "FQ-A4", "FQ-A5"})


@unique
class CheckPassed(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNMEASURED = "unmeasured"


@unique
class RubricKind(StrEnum):
    HARD = "hard"
    ADVISORY = "advisory"
    INFORMATIONAL = "informational"
    INVALID = "invalid"


@unique
class UnmeasuredPolicy(StrEnum):
    BLOCKED = "blocked"
    REVIEW = "review"
    NON_BLOCKING = "non_blocking"


@dataclass(frozen=True, slots=True)
class RubricMapPaths:
    mapping: Path
    qa_doc: Path
    rubric_doc: Path


@dataclass(frozen=True, slots=True)
class DiagnosticClassification:
    status: str
    counts_as_pass: bool


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: list[str]
    metric_count: int


@dataclass(frozen=True, slots=True)
class RubricMapError(Exception):
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.detail}"


def classify_diagnostic(entry: Mapping[str, str], passed: CheckPassed) -> DiagnosticClassification:
    rubric_id = entry.get("rubric_id", "")
    kind = _rubric_kind(rubric_id)
    policy = _policy_from_entry(entry)

    match passed:
        case CheckPassed.PASS:
            return DiagnosticClassification(status="pass", counts_as_pass=True)
        case CheckPassed.FAIL:
            return DiagnosticClassification(status=_failed_status(kind), counts_as_pass=False)
        case CheckPassed.UNMEASURED:
            return DiagnosticClassification(status=_unmeasured_status(policy), counts_as_pass=False)
        case unreachable:
            assert_never(unreachable)


def validate_rubric_map(paths: RubricMapPaths) -> ValidationResult:
    errors: list[str] = []
    data = _read_mapping(paths.mapping, errors)
    metrics = _metric_entries(data, errors)
    _validate_metric_names(metrics, errors)
    _validate_metric_entries(metrics, errors)
    _validate_docs(paths.qa_doc, errors)
    _validate_docs(paths.rubric_doc, errors)
    return ValidationResult(errors=errors, metric_count=len(metrics))


def main() -> int:
    result = validate_rubric_map(RubricMapPaths(mapping=MAP_PATH, qa_doc=QA_PATH, rubric_doc=RUBRIC_PATH))
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}")
        return 1
    print(f"geometry rubric map ok: {result.metric_count} geometry_diagnostics/1 metrics mapped exactly once")
    print(f"docs pointers ok: {DOC_POINTER}")
    return 0


def _read_mapping(path: Path, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{path}: mapping file is missing")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
        return {}


def _metric_entries(data, errors: list[str]):
    if not isinstance(data, dict):
        errors.append("mapping root must be a JSON object")
        return {}
    if data.get("source_schema_version") != "geometry_diagnostics/1":
        errors.append("source_schema_version must be geometry_diagnostics/1")
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics must be a JSON object keyed by geometry metric name")
        return {}
    return metrics


def _validate_metric_names(metrics: Mapping[str, Mapping[str, str]], errors: list[str]) -> None:
    canonical = set(GEOMETRY_METRIC_NAMES)
    mapped = set(metrics)
    missing = sorted(canonical - mapped)
    extra = sorted(mapped - canonical)
    if missing:
        errors.append(f"missing geometry metric mappings: {', '.join(missing)}")
    if extra:
        errors.append(f"unknown geometry metric mappings: {', '.join(extra)}")


def _validate_metric_entries(metrics: Mapping[str, Mapping[str, str]], errors: list[str]) -> None:
    for name in sorted(set(GEOMETRY_METRIC_NAMES) & set(metrics)):
        entry = metrics[name]
        if not isinstance(entry, dict):
            errors.append(f"{name}: mapping entry must be a JSON object")
            continue
        _validate_entry(name, entry, errors)


def _validate_entry(metric_name: str, entry: Mapping[str, str], errors: list[str]) -> None:
    rubric_id = _entry_text(entry, "rubric_id")
    if rubric_id is None:
        errors.append(f"{metric_name}: rubric_id must be a non-empty string")
        return
    kind = _rubric_kind(rubric_id)
    match kind:
        case RubricKind.HARD:
            if entry.get("unmeasured_policy", "") != UnmeasuredPolicy.BLOCKED.value:
                errors.append(f"{metric_name}: unmeasured_policy must be 'blocked'")
            if _entry_text(entry, "rationale") is None:
                errors.append(f"{metric_name}: rationale must be a non-empty string")
        case RubricKind.ADVISORY:
            if entry.get("unmeasured_policy", "") != UnmeasuredPolicy.REVIEW.value:
                errors.append(f"{metric_name}: unmeasured_policy must be 'review'")
            if _entry_text(entry, "rationale") is None:
                errors.append(f"{metric_name}: rationale must be a non-empty string")
        case RubricKind.INFORMATIONAL:
            if entry.get("unmeasured_policy", "") != UnmeasuredPolicy.NON_BLOCKING.value:
                errors.append(f"{metric_name}: unmeasured_policy must be 'non_blocking'")
            if _entry_text(entry, "non_blocking_reason") is None:
                errors.append(f"{metric_name}: non_blocking_reason must be a non-empty string")
        case RubricKind.INVALID:
            errors.append(f"{metric_name}: invalid rubric_id {rubric_id!r}")
        case unreachable:
            assert_never(unreachable)


def _validate_docs(path: Path, errors: list[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"{path}: documentation file is missing")
        return
    for required in (DOC_POINTER, CHECKER_POINTER):
        if required not in text:
            errors.append(f"{path}: missing machine-readable mapping pointer {required}")
    missing_metrics = [name for name in GEOMETRY_METRIC_NAMES if name not in text]
    if missing_metrics:
        errors.append(f"{path}: stale docs missing metric names: {', '.join(missing_metrics)}")


def _entry_text(entry: Mapping[str, str], field: str) -> str | None:
    value = entry.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _rubric_kind(rubric_id: str) -> RubricKind:
    if rubric_id in HARD_IDS:
        return RubricKind.HARD
    if rubric_id in ADVISORY_IDS:
        return RubricKind.ADVISORY
    if rubric_id == "informational":
        return RubricKind.INFORMATIONAL
    return RubricKind.INVALID


def _policy_from_entry(entry: Mapping[str, str]) -> UnmeasuredPolicy:
    raw_policy = entry.get("unmeasured_policy", "")
    try:
        return UnmeasuredPolicy(raw_policy)
    except ValueError as exc:
        raise RubricMapError(path=MAP_PATH, detail=f"invalid unmeasured_policy {raw_policy!r}") from exc


def _failed_status(kind: RubricKind) -> str:
    match kind:
        case RubricKind.HARD:
            return "blocked"
        case RubricKind.ADVISORY:
            return "review"
        case RubricKind.INFORMATIONAL:
            return "informational"
        case RubricKind.INVALID:
            return "blocked"
        case unreachable:
            assert_never(unreachable)


def _unmeasured_status(policy: UnmeasuredPolicy) -> str:
    match policy:
        case UnmeasuredPolicy.BLOCKED:
            return "blocked"
        case UnmeasuredPolicy.REVIEW:
            return "review"
        case UnmeasuredPolicy.NON_BLOCKING:
            return "informational"
        case unreachable:
            assert_never(unreachable)


if __name__ == "__main__":
    raise SystemExit(main())
