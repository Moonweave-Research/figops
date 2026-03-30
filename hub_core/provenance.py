import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime

from .runtime_paths import ensure_runtime_dirs, fallback_temp_dvc_home, resolve_dvc_home
from .utils import hash_file, is_executable_available, short_hash

DEFAULT_PYTHON_LOCK_CANDIDATES = ("uv.lock", "requirements-lock.txt")
DEFAULT_R_LOCK_CANDIDATE = "renv.lock"

def _resolve_lock_path(project_dir, hub_path, raw_path):
    lock_value = str(raw_path).strip()
    if not lock_value:
        return None
    if os.path.isabs(lock_value):
        return lock_value

    from_project = os.path.join(project_dir, lock_value)
    if os.path.exists(from_project):
        return from_project
    return os.path.join(hub_path, lock_value)

def _first_existing(paths):
    for path in paths:
        if path and os.path.exists(path):
            return path
    return None

def _inspect_lock(path):
    exists = bool(path and os.path.exists(path))
    lock_hash = hash_file(path) if exists else None
    return {"path": path, "exists": exists, "hash": lock_hash}

def _build_environment_hash(lock_info, python_version, r_version, config):
    lock_info = lock_info if isinstance(lock_info, dict) else {}
    execution = config.get("execution", {}) if isinstance(config.get("execution", {}), dict) else {}
    payload = {
        "python_version": python_version,
        "r_version": r_version,
        "strict": bool(lock_info.get("strict", False)),
        "python_lock": {
            "source": lock_info.get("python_lock", {}).get("source"),
            "exists": bool(lock_info.get("python_lock", {}).get("exists")),
            "hash": lock_info.get("python_lock", {}).get("hash"),
        },
        "r_lock": {
            "source": lock_info.get("r_lock", {}).get("source"),
            "exists": bool(lock_info.get("r_lock", {}).get("exists")),
            "hash": lock_info.get("r_lock", {}).get("hash"),
        },
        "execution": {
            "python": execution.get("python"),
            "rscript": execution.get("rscript"),
        },
    }
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def _resolve_dvc_command():
    env_cmd = os.environ.get("DVC_BIN")
    if env_cmd and _is_working_cli([env_cmd], "--version"):
        return [env_cmd]

    sibling_dvc = _sibling_dvc_executable(sys.executable)
    if sibling_dvc and _is_working_cli([sibling_dvc], "--version"):
        return [sibling_dvc]

    candidates = [
        "dvc",
        [sys.executable, "-m", "dvc"],
    ]
    for cmd in candidates:
        if _is_working_cli(cmd if isinstance(cmd, list) else [cmd], "--version"):
            return cmd if isinstance(cmd, list) else [cmd]
    return None


def _sibling_dvc_executable(python_executable):
    if not python_executable:
        return None
    python_path = os.path.abspath(str(python_executable))
    bindir = os.path.dirname(python_path)
    name = "dvc.exe" if os.name == "nt" else "dvc"
    candidate = os.path.join(bindir, name)
    if os.path.exists(candidate):
        return candidate
    return None

def _is_working_cli(cmd, version_arg):
    if not cmd:
        return False
    probe = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
    if probe and probe[0] and not probe[0].startswith("-") and not is_executable_available(probe[0]):
        return False
    try:
        proc = subprocess.run(
            probe + [version_arg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
            check=False,
        )
    except OSError:
        return False
    except Exception:
        return False
    return proc.returncode == 0

def _prepare_dvc_env(hub_path):
    base = resolve_dvc_home()
    cache_dir = os.path.join(base, "xdg_cache")
    config_dir = os.path.join(base, "xdg_config")
    state_dir = os.path.join(base, "xdg_state")
    try:
        ensure_runtime_dirs(base, cache_dir, config_dir, state_dir)
    except OSError:
        base = fallback_temp_dvc_home()
        cache_dir = os.path.join(base, "xdg_cache")
        config_dir = os.path.join(base, "xdg_config")
        state_dir = os.path.join(base, "xdg_state")
        ensure_runtime_dirs(base, cache_dir, config_dir, state_dir)

    env = os.environ.copy()
    env["DVC_HOME"] = base
    env["XDG_CACHE_HOME"] = cache_dir
    env["XDG_CONFIG_HOME"] = config_dir
    env["XDG_STATE_HOME"] = state_dir
    return env

def validate_environment_locks(project_dir, hub_path, config, strict_cli=False):
    raw_environment = config.get("environment", {})
    environment = raw_environment if isinstance(raw_environment, dict) else {}
    strict = bool(environment.get("strict", False)) or bool(strict_cli)

    explicit_python_lock = environment.get("python_lock")
    explicit_r_lock = environment.get("r_lock")

    if isinstance(explicit_python_lock, str) and explicit_python_lock.strip():
        python_path = _resolve_lock_path(project_dir, hub_path, explicit_python_lock)
        python_source = "config.environment.python_lock"
    else:
        candidates = [os.path.join(hub_path, item) for item in DEFAULT_PYTHON_LOCK_CANDIDATES]
        python_path = _first_existing(candidates) or candidates[0]
        python_source = "default"

    if isinstance(explicit_r_lock, str) and explicit_r_lock.strip():
        r_path = _resolve_lock_path(project_dir, hub_path, explicit_r_lock)
        r_source = "config.environment.r_lock"
    else:
        r_path = os.path.join(project_dir, DEFAULT_R_LOCK_CANDIDATE)
        r_source = "default"

    python_info = _inspect_lock(python_path)
    python_info["source"] = python_source
    r_info = _inspect_lock(r_path)
    r_info["source"] = r_source

    missing = []
    if not python_info["exists"]:
        missing.append("python_lock")
    if not r_info["exists"]:
        missing.append("r_lock")

    print("\n🔐 [Environment Lock Gate]")
    py_status = "OK" if python_info["exists"] else "MISSING"
    r_status = "OK" if r_info["exists"] else "MISSING"
    print(f"   - python_lock ({python_info['source']}): {python_info['path']} [{py_status}]")
    if python_info["hash"]:
        print(f"     hash: {short_hash(python_info['hash'])}")
    print(f"   - r_lock ({r_info['source']}): {r_info['path']} [{r_status}]")
    if r_info["hash"]:
        print(f"     hash: {short_hash(r_info['hash'])}")

    if missing and strict:
        print(f"   ❌ Strict mode enabled: missing lockfile(s): {', '.join(missing)}")
        print(
            "   ├─ Add the missing lockfile(s), or set "
            "environment.r_lock / environment.python_lock in project_config.yaml."
        )
        print("   └─ If you only want a local smoke run, rerun without --strict-lock.")
        return {
            "ok": False,
            "strict": strict,
            "python_lock": python_info,
            "r_lock": r_info,
        }

    if missing:
        print(f"   ⚠️  Lockfile missing: {', '.join(missing)} (continuing, non-strict mode)")
        print(
            "   └─ This run is allowed, but provenance and reproducibility "
            "are weaker until lockfiles are added."
        )
    else:
        print("   ✅ Lockfile gate passed.")

    return {
        "ok": True,
        "strict": strict,
        "python_lock": python_info,
        "r_lock": r_info,
    }

def collect_dvc_provenance(project_dir, hub_path):
    workspace_candidates = [project_dir, hub_path]
    workspace = None
    for candidate in workspace_candidates:
        if os.path.isdir(os.path.join(candidate, ".dvc")):
            workspace = candidate
            break

    if workspace is None:
        return {
            "enabled": False,
            "workspace": None,
            "status": "dvc_not_initialized",
            "status_hash": None,
        }

    dvc_cmd = _resolve_dvc_command()
    if not dvc_cmd:
        return {
            "enabled": True,
            "workspace": workspace,
            "status": "dvc_binary_not_found",
            "status_hash": None,
        }

    try:
        dvc_env = _prepare_dvc_env(hub_path)
        proc = subprocess.run(
            list(dvc_cmd) + ["status", "--json"],
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
            check=False,
            env=dvc_env,
        )
    except Exception as e:
        return {
            "enabled": True,
            "workspace": workspace,
            "status": f"dvc_status_error: {e}",
            "status_hash": None,
        }

    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        summary = output.splitlines()[0] if output else f"dvc_status_failed(rc={proc.returncode})"
        return {
            "enabled": True,
            "workspace": workspace,
            "status": summary,
            "status_hash": None,
        }

    if not output:
        normalized = "{}"
        return {
            "enabled": True,
            "workspace": workspace,
            "status": "up_to_date",
            "status_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }

    try:
        parsed = json.loads(output)
        normalized = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        changed = len(parsed) if isinstance(parsed, dict) else 1
        status = "up_to_date" if changed == 0 else f"changed_items={changed}"
    except json.JSONDecodeError:
        normalized = output
        status = "raw_status"

    return {
        "enabled": True,
        "workspace": workspace,
        "status": status,
        "status_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }

def _readable_tool_version(cmd):
    if not is_executable_available(cmd):
        return "N/A"

    candidates = (
        [cmd, "--version"],
        [cmd, "-version"],
        [cmd, "version"],
    )
    for sub_cmd in candidates:
        try:
            out = subprocess.check_output(
                sub_cmd, stderr=subprocess.STDOUT, text=True, timeout=4
            ).strip()
            if out:
                return out.splitlines()[0]
        except Exception:
            continue
    return "N/A"

def _readable_git_commit(hub_path):
    try:
        out = subprocess.check_output(
            ["git", "-C", hub_path, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3
        ).strip()
        return out if out else "N/A"
    except Exception:
        return "N/A"

def print_provenance(
    project_dir,
    config_path,
    config_hash,
    config,
    lock_info=None,
    dvc_info=None,
    build_state_path=None,
):
    # This assumes orchestrator.py is one level up from hub_core
    hub_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    execution = config.get("execution", {}) if isinstance(config.get("execution", {}), dict) else {}
    r_exec = execution.get("rscript") or "Rscript"
    timestamp = datetime.now().isoformat(timespec="seconds")

    project_hash = hashlib.sha256(os.path.abspath(project_dir).encode("utf-8")).hexdigest()
    git_commit = _readable_git_commit(hub_path)
    python_version = sys.version.split()[0]
    r_version = _readable_tool_version(r_exec)
    environment_hash = _build_environment_hash(lock_info, python_version, r_version, config)

    print("\n🧾 [Provenance]")
    print(f"   - timestamp: {timestamp}")
    print(f"   - project_path: {os.path.abspath(project_dir)}")
    print(f"   - project_hash: {short_hash(project_hash)}")
    print(f"   - config_path: {config_path}")
    print(f"   - config_hash: {short_hash(config_hash)}")
    print(f"   - git_commit: {git_commit}")
    print(f"   - python_version: {python_version}")
    print(f"   - r_version: {r_version}")
    if build_state_path:
        print(f"   - build_state: {build_state_path}")

    if isinstance(lock_info, dict):
        python_lock = lock_info.get("python_lock", {})
        r_lock = lock_info.get("r_lock", {})
        print(f"   - python_lock_hash: {short_hash(python_lock.get('hash'))}")
        print(f"   - r_lock_hash: {short_hash(r_lock.get('hash'))}")
    print(f"   - environment_hash: {short_hash(environment_hash)}")

    if isinstance(dvc_info, dict):
        print(f"   - dvc_status: {dvc_info.get('status', 'N/A')}")
        print(f"   - dvc_status_hash: {short_hash(dvc_info.get('status_hash'))}")


# ---------------------------------------------------------------------------
# Digital Fingerprint: 이미지 메타데이터 임베딩
# ---------------------------------------------------------------------------

def build_fingerprint_payload(
    project_name: str,
    config_hash: str,
    environment_hash: str,
    git_commit: str,
    timestamp: str,
    dvc_info: dict | None = None,
    data_hashes: dict | None = None,
    script: str | None = None,
    input_patterns: list[str] | None = None,
) -> dict:
    """프로방스 정보를 이미지에 임베딩할 컴팩트한 딕셔너리로 조립합니다.

    Args:
        data_hashes: {"파일명": "sha256_short"} 형태의 입력 데이터 해시 맵.
        script: 이 figure를 생성한 스크립트 경로.
    """
    payload = {
        "project": project_name,
        "config": short_hash(config_hash) if config_hash else "N/A",
        "env": short_hash(environment_hash) if environment_hash else "N/A",
        "git": git_commit or "N/A",
        "dvc": (dvc_info or {}).get("status", "N/A"),
        "ts": timestamp,
        "generator": "Graph-Hub/provenance.py",
    }
    if script:
        payload["script"] = script
    if data_hashes:
        payload["data"] = data_hashes
    if input_patterns:
        payload["input_patterns"] = input_patterns
    return payload


def _hash_input_files(project_dir: str, inputs: list) -> dict:
    """inputs 경로 목록의 파일을 해시하여 {파일명: short_hash} 맵을 반환합니다."""
    result = {}
    for inp in inputs:
        if not isinstance(inp, str):
            continue
        abs_path = os.path.join(project_dir, inp)
        if os.path.isfile(abs_path):
            h = hash_file(abs_path)
            result[os.path.basename(inp)] = short_hash(h) if h else "N/A"
        elif os.path.isdir(abs_path):
            # 디렉터리인 경우: 내부 파일 목록 해시
            dir_files = sorted(
                f for f in os.listdir(abs_path)
                if os.path.isfile(os.path.join(abs_path, f))
            )
            dir_hash = hashlib.sha256(
                "\n".join(dir_files).encode("utf-8")
            ).hexdigest()
            result[os.path.basename(inp) + "/"] = short_hash(dir_hash)
    return result


def embed_provenance_fingerprint(output_path: str, fingerprint: dict) -> bool:
    """
    PNG / PDF / SVG 파일에 프로방스 정보를 메타데이터로 임베딩합니다.

    - PNG  : PIL PngInfo tEXt 청크 (속성 보기 → 세부 정보에서 확인 가능)
    - PDF  : pypdf XMP 메타데이터 (pypdf 미설치 시 건너뜀)
    - SVG  : XML 주석 (<!-- Research-Fingerprint: {...} -->)

    성공 여부를 반환합니다.
    """
    if not os.path.exists(output_path):
        return False

    payload_str = json.dumps(fingerprint, ensure_ascii=False, separators=(",", ":"))
    ext = os.path.splitext(output_path)[1].lower()

    if ext == ".png":
        return _embed_png_fingerprint(output_path, payload_str)
    if ext == ".pdf":
        return _embed_pdf_fingerprint(output_path, payload_str)
    if ext == ".svg":
        return _embed_svg_fingerprint(output_path, payload_str)

    return False


def _embed_png_fingerprint(path: str, payload_str: str) -> bool:
    """PIL tEXt 청크에 Research-Fingerprint 키로 임베딩합니다."""
    try:
        from PIL import Image, PngImagePlugin
    except ImportError:
        return False

    try:
        img = Image.open(path)
        meta = PngImagePlugin.PngInfo()

        # 기존 메타데이터 보존
        existing = img.info or {}
        for key, val in existing.items():
            if isinstance(key, str) and isinstance(val, str):
                meta.add_text(key, val)

        meta.add_text("Research-Fingerprint", payload_str)
        img.save(path, pnginfo=meta)
        img.close()
        return True
    except Exception:
        return False


def _embed_pdf_fingerprint(path: str, payload_str: str) -> bool:
    """pypdf XMP 메타데이터에 임베딩합니다. pypdf 미설치 시 건너뜁니다."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return False  # 선택적 의존성, 미설치 시 조용히 건너뜀

    tmp = path + ".tmp_fingerprint"
    try:
        parsed = json.loads(payload_str) if isinstance(payload_str, str) else {}
        reader = PdfReader(path)
        writer = PdfWriter()
        writer.append(reader)
        writer.add_metadata({
            "/Research-Fingerprint": payload_str,
            "/Research-Config-Hash": parsed.get("config", ""),
            "/Research-Env-Hash": parsed.get("env", ""),
        })
        with open(tmp, "wb") as f:
            writer.write(f)
        os.replace(tmp, path)
        return True
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def _embed_svg_fingerprint(path: str, payload_str: str) -> bool:
    """SVG 파일 선두에 XML 주석으로 임베딩합니다."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()

        comment = f"<!-- Research-Fingerprint: {payload_str} -->"

        # <?xml ... ?> 선언 직후 삽입, 없으면 파일 선두에 삽입
        if "?>" in content:
            idx = content.index("?>") + 2
            content = content[:idx] + "\n" + comment + content[idx:]
        else:
            content = comment + "\n" + content

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


def embed_figures_fingerprint(
    project_dir: str,
    config: dict,
    config_hash: str,
    environment_hash: str,
    git_commit: str,
    timestamp: str,
    dvc_info: dict | None = None,
) -> int:
    """
    project_config.yaml의 figures/diagrams 섹션에 정의된 모든 출력 파일에
    프로방스 지문(Digital Fingerprint)을 임베딩합니다.

    Returns:
        임베딩에 성공한 파일 수.
    """
    project_name = config.get("project", {}).get("name", os.path.basename(project_dir))
    base_fingerprint_kwargs = dict(
        project_name=project_name,
        config_hash=config_hash,
        environment_hash=environment_hash,
        git_commit=git_commit,
        timestamp=timestamp,
        dvc_info=dvc_info,
    )

    # 1) config 등록 파일 수집 — inputs/script 메타 포함
    # {정규화 경로: {"inputs": [...], "script": "..."}}
    config_meta: dict[str, dict] = {}
    for entry in config.get("figures", []) + config.get("diagrams", []):
        if not (isinstance(entry, dict) and entry.get("output")):
            continue
        norm = os.path.normpath(os.path.join(project_dir, entry["output"]))
        config_meta[norm] = {
            "inputs": entry.get("inputs", []),
            "script": entry.get("script", ""),
        }

    # 2) results/figures/ 디렉터리 전체 스캔 (config 미등록 파일 포함)
    discovered_paths: set[str] = set()
    results_figures_dir = os.path.join(project_dir, "results", "figures")
    if os.path.isdir(results_figures_dir):
        for root, _, files in os.walk(results_figures_dir):
            for fname in files:
                if os.path.splitext(fname)[1].lower() in {".png", ".pdf", ".svg"}:
                    discovered_paths.add(os.path.normpath(os.path.join(root, fname)))

    all_paths = set(config_meta.keys()) | discovered_paths
    unregistered = discovered_paths - set(config_meta.keys())
    if unregistered:
        print(
            f"   ℹ️  {len(unregistered)} unregistered figure(s) found in "
            f"results/figures/ — tagging all."
        )

    embedded = 0
    skipped = []
    for path in sorted(all_paths):
        if not os.path.exists(path):
            continue

        # config 등록 파일은 inputs/script 해시 포함, 미등록 파일은 기본 지문만
        meta = config_meta.get(path, {})
        data_hashes = (
            _hash_input_files(project_dir, meta["inputs"])
            if meta.get("inputs")
            else None
        )
        fingerprint = build_fingerprint_payload(
            **base_fingerprint_kwargs,
            data_hashes=data_hashes,
            script=meta.get("script") or None,
        )

        if embed_provenance_fingerprint(path, fingerprint):
            embedded += 1
        else:
            skipped.append(os.path.basename(path))

    print(f"\n🔏 [Digital Fingerprint] {embedded} file(s) tagged.")
    if skipped:
        print(f"   ⚠️  Skipped (dependency missing or error): {', '.join(skipped)}")

    return embedded


def read_provenance_fingerprint(path: str) -> dict | None:
    """
    PNG / PDF / SVG 파일에서 임베딩된 프로방스 정보를 읽어옵니다.
    """
    if not os.path.exists(path):
        return None

    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        return _read_png_fingerprint(path)
    if ext == ".pdf":
        return _read_pdf_fingerprint(path)
    if ext == ".svg":
        return _read_svg_fingerprint(path)
    return None


def _read_png_fingerprint(path: str) -> dict | None:
    try:
        from PIL import Image
        with Image.open(path) as img:
            raw = img.info.get("Research-Fingerprint")
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return None


def _read_pdf_fingerprint(path: str) -> dict | None:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        meta = reader.metadata
        if meta and "/Research-Fingerprint" in meta:
            return json.loads(meta["/Research-Fingerprint"])
    except Exception:
        pass
    return None


def _read_svg_fingerprint(path: str) -> dict | None:
    try:
        import re
        with open(path, encoding="utf-8") as f:
            # 주석 형태 탐색: <!-- Research-Fingerprint: {...} -->
            content = f.read(4096)  # 성능을 위해 선두 4KB만 읽음
            match = re.search(r"<!-- Research-Fingerprint:\s*({.*?})\s*-->", content)
            if match:
                return json.loads(match.group(1))
    except Exception:
        pass
    return None
