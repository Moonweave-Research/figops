import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .logging import get_logger
from .provenance_inputs import expand_project_input_files
from .utils import hash_file, is_executable_available, short_hash

DEFAULT_PYTHON_LOCK_CANDIDATES = ("uv.lock",)
DEFAULT_R_LOCK_CANDIDATE = "renv.lock"

logger = get_logger(__name__)


def reproducible_timestamp() -> str:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH", "1")
    if not raw_epoch.isascii() or not raw_epoch.isdigit():
        raise ValueError("SOURCE_DATE_EPOCH must be a nonnegative integer")
    try:
        timestamp = datetime.fromtimestamp(int(raw_epoch), tz=timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError("SOURCE_DATE_EPOCH is outside the supported timestamp range") from exc
    return timestamp.isoformat(timespec="seconds")


def hash_csv_file(csv_path: str | Path) -> str:
    path = Path(csv_path)
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


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

    logger.info("\n🔐 [Environment Lock Gate]")
    py_status = "OK" if python_info["exists"] else "MISSING"
    r_status = "OK" if r_info["exists"] else "MISSING"
    logger.info("   - python_lock (%s): %s [%s]", python_info["source"], python_info["path"], py_status)
    if python_info["hash"]:
        logger.info("     hash: %s", short_hash(python_info["hash"]))
    logger.info("   - r_lock (%s): %s [%s]", r_info["source"], r_info["path"], r_status)
    if r_info["hash"]:
        logger.info("     hash: %s", short_hash(r_info["hash"]))

    if missing and strict:
        logger.info("   ❌ Strict mode enabled: missing lockfile(s): %s", ", ".join(missing))
        logger.info(
            "   ├─ Add the missing lockfile(s), or set "
            "environment.r_lock / environment.python_lock in project_config.yaml."
        )
        logger.info("   └─ If you only want a local smoke run, rerun without --strict-lock.")
        return {
            "ok": False,
            "strict": strict,
            "python_lock": python_info,
            "r_lock": r_info,
        }

    if missing:
        logger.info("   ⚠️  Lockfile missing: %s (continuing, non-strict mode)", ", ".join(missing))
        logger.info(
            "   └─ This run is allowed, but provenance and reproducibility are weaker until lockfiles are added."
        )
    else:
        logger.info("   ✅ Lockfile gate passed.")

    return {
        "ok": True,
        "strict": strict,
        "python_lock": python_info,
        "r_lock": r_info,
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
            out = subprocess.check_output(sub_cmd, stderr=subprocess.STDOUT, text=True, timeout=4).strip()
            if out:
                return out.splitlines()[0]
        except Exception:
            continue
    return "N/A"


def _readable_git_commit(hub_path):
    try:
        out = subprocess.check_output(
            ["git", "-C", hub_path, "rev-parse", "--short", "HEAD"], stderr=subprocess.STDOUT, text=True, timeout=3
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
    build_state_path=None,
):
    # This assumes orchestrator.py is one level up from hub_core
    hub_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    execution = config.get("execution", {}) if isinstance(config.get("execution", {}), dict) else {}
    r_exec = execution.get("rscript") or "Rscript"
    timestamp = datetime.now().isoformat(timespec="seconds")

    project_hash = hashlib.sha256(os.path.abspath(project_dir).encode("utf-8")).hexdigest()
    git_commit = _readable_git_commit(hub_path)
    python_version = sys.version.split()[0]
    r_version = _readable_tool_version(r_exec)
    environment_hash = _build_environment_hash(lock_info, python_version, r_version, config)

    logger.info("\n🧾 [Provenance]")
    logger.info("   - timestamp: %s", timestamp)
    logger.info("   - project_path: %s", os.path.abspath(project_dir))
    logger.info("   - project_hash: %s", short_hash(project_hash))
    logger.info("   - config_path: %s", config_path)
    logger.info("   - config_hash: %s", short_hash(config_hash))
    logger.info("   - git_commit: %s", git_commit)
    logger.info("   - python_version: %s", python_version)
    logger.info("   - r_version: %s", r_version)
    if build_state_path:
        logger.info("   - build_state: %s", build_state_path)

    if isinstance(lock_info, dict):
        python_lock = lock_info.get("python_lock", {})
        r_lock = lock_info.get("r_lock", {})
        logger.info("   - python_lock_hash: %s", short_hash(python_lock.get("hash")))
        logger.info("   - r_lock_hash: %s", short_hash(r_lock.get("hash")))
    logger.info("   - environment_hash: %s", short_hash(environment_hash))


# ---------------------------------------------------------------------------
# Digital Fingerprint: 이미지 메타데이터 임베딩
# ---------------------------------------------------------------------------


def build_fingerprint_payload(
    project_name: str,
    config_hash: str,
    environment_hash: str,
    git_commit: str,
    timestamp: str,
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


def hash_input_files(project_dir: str, inputs: list[str]) -> dict[str, str]:
    project_root = Path(project_dir).resolve(strict=True)
    result: dict[str, str] = {}
    for path in expand_project_input_files(project_root, inputs, require_matches=False):
        digest = hash_file(path)
        result[path.relative_to(project_root).as_posix()] = short_hash(digest) if digest else "N/A"
    return result


def _hash_input_files(project_dir: str, inputs: list[str]) -> dict[str, str]:
    return hash_input_files(project_dir, inputs)


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
        save_kwargs = {}
        if isinstance(existing.get("dpi"), tuple):
            save_kwargs["dpi"] = existing["dpi"]

        meta.add_text("Research-Fingerprint", payload_str)
        img.save(path, pnginfo=meta, **save_kwargs)
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
        writer.add_metadata(
            {
                "/Research-Fingerprint": payload_str,
                "/Research-Config-Hash": parsed.get("config", ""),
                "/Research-Env-Hash": parsed.get("env", ""),
            }
        )
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
        logger.info("   ℹ️  %s unregistered figure(s) found in results/figures/ — tagging all.", len(unregistered))

    embedded = 0
    skipped = []
    for path in sorted(all_paths):
        if not os.path.exists(path):
            continue

        # config 등록 파일은 inputs/script 해시 포함, 미등록 파일은 기본 지문만
        meta = config_meta.get(path, {})
        data_hashes = _hash_input_files(project_dir, meta["inputs"]) if meta.get("inputs") else None
        fingerprint = build_fingerprint_payload(
            **base_fingerprint_kwargs,
            data_hashes=data_hashes,
            script=meta.get("script") or None,
            input_patterns=list(meta.get("inputs") or []),
        )

        if embed_provenance_fingerprint(path, fingerprint):
            embedded += 1
        else:
            skipped.append(os.path.basename(path))

    logger.info("\n🔏 [Digital Fingerprint] %s file(s) tagged.", embedded)
    if skipped:
        logger.info("   ⚠️  Skipped (dependency missing or error): %s", ", ".join(skipped))

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
