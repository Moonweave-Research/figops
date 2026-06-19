"""
Failure snapshot helpers for Graph Hub pipeline runs.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .logging import get_logger
from .runtime_paths import resolve_execution_artifacts_dir, resolve_latest_publish_dir

logger = get_logger(__name__)


def dump_exception_failure(
    project_dir: str | Path,
    exc: BaseException,
    *,
    context: dict | None = None,
    max_frames: int = 3,
    max_locals: int = 8,
) -> str:
    """Write a structured exception snapshot to results/latest_failure.json."""
    tb = traceback.TracebackException.from_exception(exc, capture_locals=True)
    frames = list(tb.stack)[-max_frames:]
    payload = {
        "timestamp_utc": _utc_now(),
        "failure_kind": "exception",
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback_tail": [
            {
                "file": frame.filename,
                "line": frame.lineno,
                "function": frame.name,
                "code": (frame.line or "").strip(),
                "locals": _trim_locals(frame.locals or {}, limit=max_locals),
            }
            for frame in frames
        ],
        "context": context or {},
    }
    return _write_payload(project_dir, payload)


def dump_pipeline_failure(
    project_dir: str | Path,
    *,
    message: str,
    context: dict | None = None,
) -> str:
    """Write a structured non-exception pipeline failure snapshot."""
    payload = {
        "timestamp_utc": _utc_now(),
        "failure_kind": "pipeline_failure",
        "exception_type": "PipelineStepFailed",
        "message": message,
        "traceback_tail": [],
        "context": context or {},
    }
    return _write_payload(project_dir, payload)


def _write_payload(project_dir: str | Path, payload: dict) -> str:
    project_path = Path(project_dir).expanduser().resolve()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    engine_target = str(context.get("engine_target") or "hub_pipeline").strip() or "hub_pipeline"
    job_id = str(context.get("job_id") or project_path.name or "hub_project")
    failure_stage = str(context.get("failure_stage") or "EXECUTE")
    raw_request = context.get("raw_request")

    payload["engine_target"] = engine_target
    payload["job_id"] = job_id
    payload["failure_stage"] = failure_stage
    payload["artifacts_dir"] = resolve_execution_artifacts_dir(str(project_path), engine_target)
    payload["latest_dir"] = resolve_latest_publish_dir(engine_target, job_id)
    if raw_request:
        payload["request"] = {"raw_request": str(raw_request)}

    output_path = project_path / "results" / "latest_failure.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    latest_failure_path = Path(payload["latest_dir"]) / "failure.json"
    latest_failure_path.parent.mkdir(parents=True, exist_ok=True)
    latest_failure_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output_path)


def _trim_locals(local_map: dict[str, object], *, limit: int) -> dict[str, str]:
    trimmed: dict[str, str] = {}
    for index, (key, value) in enumerate(local_map.items()):
        if index >= limit:
            trimmed["..."] = f"{len(local_map) - limit} more"
            break
        text = value if isinstance(value, str) else repr(value)
        trimmed[key] = text[:300]
    return trimmed


def dump_contract_report(
    project_dir: str | Path,
    csv_path: str,
    violations: list[dict[str, str]],
) -> str | None:
    """
    데이터 계약 위반 목록을 Markdown 진단 리포트로 저장하고 터미널에 즉시 출력합니다.

    violations 각 항목은 다음 키를 가집니다:
      row, column, value, expected, violation_type

    위반이 없으면 None을 반환합니다 (clean pass).
    """
    if not violations:
        return None

    project_path = Path(project_dir).expanduser().resolve()
    diag_dir = project_path / "results" / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_name = f"contract_report_{ts}.md"
    report_path = diag_dir / report_name

    lines = [
        f"## 🚨 Data Contract Violations -- {csv_path}",
        f"_Generated: {_utc_now()}_\n",
        "| Row | Column | Value | Expected | Violation |",
        "| --- | ------ | ----- | -------- | --------- |",
    ]
    for v in violations:
        row = v.get("row", "?")
        col = v.get("column", "?")
        val = str(v.get("value", ""))[:40]
        exp = str(v.get("expected", ""))[:40]
        vtype = v.get("violation_type", "unknown")
        lines.append(f"| {row} | {col} | {val} | {exp} | {vtype} |")

    lines.append(f"\n**Total violations**: {len(violations)}")

    md_content = "\n".join(lines)
    report_path.write_text(md_content, encoding="utf-8")

    # Rich CLI Diagnostics: Only if in a TTY
    try:
        if sys.stdout.isatty():
            from rich.console import Console
            from rich.markdown import Markdown
            console = Console(stderr=True)
            console.print("\n")
            console.print(Markdown(md_content))
            console.print(f"📄 Report saved: [bold cyan]{report_path}[/bold cyan]\n")
        else:
            logger.info("\n[Contract Violations] Report saved: %s", report_path)
    except ImportError:
        logger.info("\n[Contract Violations] Report saved: %s", report_path)

    return str(report_path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
