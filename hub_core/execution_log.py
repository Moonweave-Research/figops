import json
import os
import shlex
import sys
import tempfile
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

from .logging import get_logger
from .provenance import _build_environment_hash, _readable_git_commit, _readable_tool_version
from .runtime_paths import (
    ensure_runtime_dirs,
    resolve_execution_artifacts_dir,
    resolve_hub_logs_dir,
    resolve_latest_publish_dir,
    resolve_runtime_root,
)

logger = get_logger(__name__)

DEFAULT_LOG_DIRNAME = "hub_logs"
DEFAULT_LOG_FILENAME = "execution_history.jsonl"
MANIFEST_VERSION = 1
STATUS_VERSION = 1
DEFAULT_ENGINE_TARGET = "hub_pipeline"


def _append_jsonl(log_dir, filename, record):
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, filename)
    with open(log_path, "a", encoding="utf-8") as f:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        f.write(line)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    return log_path


def _normalize_args(args):
    if isinstance(args, Namespace):
        args = vars(args)
    if not isinstance(args, dict):
        return {}
    normalized = {}
    for key in sorted(args.keys()):
        value = args[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized[key] = value
        else:
            normalized[key] = str(value)
    return normalized


def build_execution_log_record(
    project_dir,
    hub_path,
    config,
    config_path,
    config_hash,
    *,
    args=None,
    lock_info=None,
    build_state_path=None,
    start_time=None,
    end_time=None,
    success=None,
    failure_stage="",
    message="",
    detail="",
    raw_request=None,
    engine_target=DEFAULT_ENGINE_TARGET,
    attempt_provenance=None,
):
    config = config if isinstance(config, dict) else {}
    execution = config.get("execution", {}) if isinstance(config.get("execution", {}), dict) else {}
    r_exec = execution.get("rscript") or "Rscript"
    python_version = sys.version.split()[0]
    r_version = _readable_tool_version(r_exec)
    environment_hash = _build_environment_hash(lock_info, python_version, r_version, config)

    started_at = _coerce_datetime(start_time)
    finished_at = _coerce_datetime(end_time)
    duration_seconds = None
    if started_at and finished_at:
        duration_seconds = round((finished_at - started_at).total_seconds(), 3)

    project_dir = os.path.abspath(project_dir)
    job_id = _infer_job_id(project_dir)
    normalized_engine_target = _normalize_engine_target(engine_target)
    artifacts_dir = resolve_execution_artifacts_dir(project_dir, normalized_engine_target)
    latest_dir = resolve_latest_publish_dir(normalized_engine_target, job_id)
    raw_request = raw_request or _default_raw_request(args)
    project_name = None
    project = config.get("project", {})
    if isinstance(project, dict):
        raw_name = project.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            project_name = raw_name.strip()

    lock_info = lock_info if isinstance(lock_info, dict) else {}

    record = {
        "artifacts_dir": artifacts_dir,
        "build_state_path": build_state_path,
        "config_hash": config_hash,
        "config_path": config_path,
        "detail": detail,
        "duration_seconds": duration_seconds,
        "engine_target": normalized_engine_target,
        "end_time": finished_at.isoformat(timespec="seconds") if finished_at else None,
        "environment_hash": environment_hash,
        "failure_stage": failure_stage,
        "git_commit": _readable_git_commit(hub_path),
        "job_id": job_id,
        "latest_dir": latest_dir,
        "lock_strict": bool(lock_info.get("strict", False)),
        "message": message,
        "project_dir": project_dir,
        "project_name": project_name,
        "python_lock_hash": lock_info.get("python_lock", {}).get("hash"),
        "python_version": python_version,
        "r_lock_hash": lock_info.get("r_lock", {}).get("hash"),
        "r_version": r_version,
        "run_args": _normalize_args(args),
        "schema_version": 1,
        "start_time": started_at.isoformat(timespec="seconds") if started_at else None,
        "status": "success" if success else "failed",
        "success": bool(success),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if isinstance(attempt_provenance, dict):
        record["attempt_provenance"] = attempt_provenance
    if raw_request:
        record["request"] = {"raw_request": raw_request}
    return record


def append_execution_log(hub_path, record, *, log_dirname=DEFAULT_LOG_DIRNAME, filename=DEFAULT_LOG_FILENAME):
    if not isinstance(record, dict):
        raise RuntimeError("Execution log record must be a dict.")

    runtime_root = resolve_runtime_root()
    if log_dirname is None:
        log_dir = resolve_hub_logs_dir()
    elif os.path.isabs(log_dirname):
        log_dir = log_dirname
    else:
        log_dir = os.path.join(runtime_root, log_dirname)
    log_path = os.path.join(log_dir, filename)

    try:
        log_path = _append_jsonl(log_dir, filename, record)
    except OSError as exc:
        fallback_dir = os.path.join(tempfile.gettempdir(), "figops", DEFAULT_LOG_DIRNAME)
        logger.warning("⚠️  Execution logging failed at primary path: %s\n   └─ %s", log_path, exc)
        logger.info("   ↪ Retrying with fallback log dir: %s", fallback_dir)
        try:
            log_path = _append_jsonl(fallback_dir, filename, record)
        except OSError as fallback_exc:
            logger.error("❌ Execution logging failed: %s\n   └─ %s", fallback_dir, fallback_exc)
            raise RuntimeError(f"failed to append execution log: {fallback_dir}") from fallback_exc

    logger.info("🗂️  Execution log appended: %s", log_path)
    return log_path


def write_execution_log(
    project_dir,
    hub_path,
    config,
    config_path,
    config_hash,
    *,
    args=None,
    lock_info=None,
    build_state_path=None,
    start_time=None,
    end_time=None,
    success=None,
    failure_stage="",
    message="",
    detail="",
    raw_request=None,
    engine_target=DEFAULT_ENGINE_TARGET,
    attempt_provenance=None,
    log_dirname=DEFAULT_LOG_DIRNAME,
    filename=DEFAULT_LOG_FILENAME,
):
    record = build_execution_log_record(
        project_dir,
        hub_path,
        config,
        config_path,
        config_hash,
        args=args,
        lock_info=lock_info,
        build_state_path=build_state_path,
        start_time=start_time,
        end_time=end_time,
        success=success,
        failure_stage=failure_stage,
        message=message,
        detail=detail,
        raw_request=raw_request,
        engine_target=engine_target,
        attempt_provenance=attempt_provenance,
    )
    log_path = append_execution_log(hub_path, record, log_dirname=log_dirname, filename=filename)
    _persist_execution_contract(record)
    return log_path, record


def _coerce_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return None


def _persist_execution_contract(record):
    artifacts_dir = Path(record["artifacts_dir"])
    latest_dir = Path(record["latest_dir"])
    ensure_runtime_dirs(str(artifacts_dir), str(latest_dir))

    manifest_path = artifacts_dir / "manifest.json"
    status_path = artifacts_dir / "status.json"
    latest_manifest_path = latest_dir / "manifest.json"
    latest_status_path = latest_dir / "status.json"

    existing_manifest = {}
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing_manifest = {}

    manifest_payload = {
        "manifest_version": MANIFEST_VERSION,
        "engine_target": record["engine_target"],
        "artifacts_dir": record["artifacts_dir"],
        "latest_dir": record["latest_dir"],
        "job_id": record["job_id"],
        "project_dir": record["project_dir"],
        "project_name": record.get("project_name"),
        "config_path": record.get("config_path"),
        "config_hash": record.get("config_hash"),
        "build_state_path": record.get("build_state_path"),
        "environment_hash": record.get("environment_hash"),
        "git_commit": record.get("git_commit"),
        "request": record.get("request", {}),
        "attempt_provenance": record.get("attempt_provenance"),
        "result": {
            "success": record["success"],
            "message": record.get("message") or _default_status_message(record["success"]),
            "failure_stage": record.get("failure_stage", ""),
            "detail": record.get("detail", ""),
            "output_path": str(Path(record["project_dir"]) / "results"),
        },
        "start_time": record.get("start_time"),
        "end_time": record.get("end_time"),
        "duration_seconds": record.get("duration_seconds"),
        "created_at": existing_manifest.get("created_at") or record["timestamp"],
        "updated_at": record["timestamp"],
    }
    status_payload = {
        "status_version": STATUS_VERSION,
        "status": record["status"],
        "failure_stage": record.get("failure_stage", ""),
        "message": record.get("message") or _default_status_message(record["success"]),
        "detail": record.get("detail", ""),
        "updated_at": record["timestamp"],
        "engine_target": record["engine_target"],
        "artifacts_dir": record["artifacts_dir"],
        "latest_dir": record["latest_dir"],
        "job_id": record["job_id"],
        "attempt_provenance": record.get("attempt_provenance"),
    }

    for path, payload in (
        (manifest_path, manifest_payload),
        (status_path, status_payload),
        (latest_manifest_path, manifest_payload),
        (latest_status_path, status_payload),
    ):
        _write_json(path, payload)


def _infer_job_id(project_dir):
    name = Path(project_dir).expanduser().resolve().name
    return name or "hub_project"


def _normalize_engine_target(engine_target):
    text = str(engine_target or DEFAULT_ENGINE_TARGET).strip()
    return text or DEFAULT_ENGINE_TARGET


def _default_raw_request(args):
    normalized = _normalize_args(args)
    parts = ["python", "orchestrator.py"]
    for key, value in normalized.items():
        if value in (None, False):
            continue
        flag = f"--{str(key).replace('_', '-')}"
        if value is True:
            parts.append(flag)
        else:
            parts.extend([flag, str(value)])
    return shlex.join(parts)


def _default_status_message(success):
    return "Hub pipeline completed successfully." if success else "Hub pipeline failed."


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
