import hashlib
import json
import os
from datetime import datetime

from .utils import normalize_string_list, resolve_path

CACHE_STRATEGY_MTIME = "mtime"
CACHE_STRATEGY_CONTENT_HASH = "content_hash"

BUILD_STATE_FILENAME = ".build_state.json"
BUILD_STATE_SCHEMA_VERSION = 3

def _normalize_record_path(abs_path, project_dir):
    abs_norm = os.path.abspath(abs_path)
    try:
        rel = os.path.relpath(abs_norm, project_dir)
    except ValueError:
        return abs_norm
    if rel.startswith(".."):
        return abs_norm
    return rel

def _sha256_of_file(abs_path: str) -> str:
    h = hashlib.sha256()
    with open(abs_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_signature(abs_path, project_dir, cache_strategy=CACHE_STRATEGY_MTIME):
    abs_norm = os.path.abspath(abs_path)
    signature = {
        "path": _normalize_record_path(abs_norm, project_dir),
        "exists": os.path.exists(abs_norm),
    }
    if not signature["exists"]:
        return signature

    try:
        stat = os.stat(abs_norm)
    except OSError:
        signature["exists"] = False
        return signature

    signature["size"] = stat.st_size
    if cache_strategy == CACHE_STRATEGY_CONTENT_HASH:
        try:
            signature["content_hash"] = _sha256_of_file(abs_norm)
        except OSError:
            signature["mtime_ns"] = stat.st_mtime_ns
    else:
        signature["mtime_ns"] = stat.st_mtime_ns
    return signature

def collect_signatures(project_dir, rel_paths, cache_strategy=CACHE_STRATEGY_MTIME):
    signatures = []
    for rel_path in normalize_string_list(rel_paths):
        abs_path = resolve_path(project_dir, rel_path)
        signatures.append(_file_signature(abs_path, project_dir, cache_strategy=cache_strategy))
    signatures.sort(key=lambda item: item["path"])
    return signatures

def file_signature(abs_path, project_dir, cache_strategy=CACHE_STRATEGY_MTIME):
    return _file_signature(abs_path, project_dir, cache_strategy=cache_strategy)

def _empty_build_state():
    return {
        "version": BUILD_STATE_SCHEMA_VERSION,
        "config_hash": None,
        "analysis": {},
        "figures": {},
        "diagrams": {},
    }

def build_state_path(project_dir):
    return os.path.join(project_dir, BUILD_STATE_FILENAME)

def load_build_state(project_dir):
    state_path = build_state_path(project_dir)
    if not os.path.exists(state_path):
        return _empty_build_state(), state_path

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"⚠️  Warning: invalid build state, resetting cache: {state_path}")
        return _empty_build_state(), state_path

    if not isinstance(state, dict):
        print(f"⚠️  Warning: malformed build state, resetting cache: {state_path}")
        return _empty_build_state(), state_path

    normalized = _empty_build_state()
    normalized["version"] = state.get("version", BUILD_STATE_SCHEMA_VERSION)
    normalized["config_hash"] = state.get("config_hash")
    normalized["analysis"] = state.get("analysis", {}) if isinstance(state.get("analysis"), dict) else {}
    normalized["figures"] = state.get("figures", {}) if isinstance(state.get("figures"), dict) else {}
    normalized["diagrams"] = state.get("diagrams", {}) if isinstance(state.get("diagrams"), dict) else {}
    return normalized, state_path

def save_build_state(state_path, build_state):
    tmp_path = f"{state_path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(build_state, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, state_path)
        return True
    except OSError as e:
        print(f"⚠️  Warning: failed to save build state: {state_path}\n   └─ {e}")
        return False

def is_step_stale(step_kind, step_key, signature, output_signatures, build_state, config_hash, force=False):
    if force:
        return True, "forced by --force"

    if int(build_state.get("version", 0)) != BUILD_STATE_SCHEMA_VERSION:
        return True, "build-state schema changed"

    prev_config_hash = build_state.get("config_hash")
    if prev_config_hash and prev_config_hash != config_hash:
        return True, "project_config.yaml modified"

    bucket = build_state.get(step_kind, {})
    prev = bucket.get(step_key) if isinstance(bucket, dict) else None
    if not prev:
        return True, "no previous build record"

    if prev.get("signature") != signature:
        return True, "script/input signature changed"

    current_missing = [out["path"] for out in output_signatures if not out.get("exists")]
    if current_missing:
        return True, f"missing outputs: {', '.join(current_missing)}"

    if prev.get("outputs") != output_signatures:
        return True, "output signature changed"

    return False, "unchanged"

def record_step_state(build_state, step_kind, step_key, signature, outputs, config_hash):
    if step_kind not in build_state or not isinstance(build_state.get(step_kind), dict):
        build_state[step_kind] = {}
    build_state["version"] = BUILD_STATE_SCHEMA_VERSION
    build_state["config_hash"] = config_hash
    build_state[step_kind][step_key] = {
        "signature": signature,
        "outputs": outputs,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
