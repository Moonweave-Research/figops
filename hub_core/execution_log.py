from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_execution_log(
    project_dir: str,
    hub_root: str,
    config: dict[str, Any],
    config_path: str,
    config_hash: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    success: bool = True,
    failure_stage: str = "",
    message: str = "",
    raw_request: str = "",
) -> tuple[str, dict[str, Any]]:
    """Write a hub pipeline execution record to disk.

    Creates manifest.json + status.json in the project artifacts dir and the
    runtime _latest dir. Appends a JSONL line to the hub execution history log.

    Returns (log_path, record) where record["job_id"] identifies the run.
    """
    job_id = str(uuid.uuid4())
    ts = (end_time or datetime.now(timezone.utc)).isoformat()
    status_str = "success" if success else "failed"

    record: dict[str, Any] = {
        "job_id": job_id,
        "project_dir": str(project_dir),
        "project_name": Path(project_dir).name,
        "engine_target": "hub_pipeline",
        "status": status_str,
        "failure_stage": failure_stage,
        "message": message,
        "start_time": (start_time.isoformat() if start_time else ""),
        "end_time": ts,
        "config_path": str(config_path),
        "config_hash": str(config_hash),
        "raw_request": raw_request,
    }

    runtime_root_env = os.environ.get("RESEARCH_HUB_RUNTIME_ROOT")
    runtime_root = Path(runtime_root_env) if runtime_root_env else Path(hub_root).parent / "hub_runtime"

    log_dir = runtime_root / "hub_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "execution_history.jsonl"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    artifacts_dir = Path(project_dir) / "results" / "_execution" / "hub_pipeline"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "manifest.json").write_text(
        json.dumps({"job_id": job_id, "config_hash": config_hash}), encoding="utf-8"
    )
    (artifacts_dir / "status.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": status_str,
                "failure_stage": failure_stage,
                "message": message,
                "updated_at": ts,
            }
        ),
        encoding="utf-8",
    )

    latest_dir = runtime_root / "_latest" / "hub_pipeline" / job_id
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "manifest.json").write_text(
        json.dumps({"job_id": job_id, "config_hash": config_hash}), encoding="utf-8"
    )
    (latest_dir / "status.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": status_str,
                "failure_stage": failure_stage,
                "message": message,
                "updated_at": ts,
            }
        ),
        encoding="utf-8",
    )

    return str(log_path), record
