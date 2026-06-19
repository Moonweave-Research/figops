import csv
import glob
import hashlib
import os
import shutil
import sys

from .logging import get_logger

logger = get_logger(__name__)

def resolve_path(base_dir, path):
    return path if os.path.isabs(path) else os.path.join(base_dir, path)

def get_hub_path():
    """
    RESEARCH_HUB_PATH 환경 변수를 반환하거나, 현재 파일 위치를 기준으로 자동 계산합니다.
    없으면 현재 작업 디렉토리(cwd)를 반환하여 Zero-Friction을 보장합니다.
    """
    path = os.environ.get("RESEARCH_HUB_PATH")
    if path:
        return os.path.abspath(path)

    # hub_core/utils.py -> graph-making-hub
    try:
        calculated = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if os.path.exists(calculated):
            return calculated
    except Exception:
        pass

    return os.getcwd()

def get_research_root():
    """
    PROJECT_ROOT 환경 변수를 반환하거나, RESEARCH_HUB_PATH의 상위 디렉토리를 반환합니다.
    최종 Fallback으로 현재 작업 디렉토리를 사용합니다.
    """
    path = os.environ.get("PROJECT_ROOT")
    if path:
        return os.path.abspath(path)

    hub_path = get_hub_path()
    try:
        calculated = os.path.abspath(os.path.join(hub_path, ".."))
        if os.path.exists(calculated):
            return calculated
    except Exception:
        pass

    return os.getcwd()

def short_hash(value, size=12):
    if value is None:
        return "N/A"
    text = str(value)
    return text[:size] if text else "N/A"

def hash_file(path):
    try:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None

def normalize_string_list(items):
    if items is None:
        return []
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def expand_declared_paths(base_dir, paths):
    expanded = []
    for raw_path in normalize_string_list(paths):
        abs_path = resolve_path(base_dir, raw_path)
        if glob.has_magic(abs_path):
            matches = sorted(
                match for match in glob.glob(abs_path, recursive=True)
                if os.path.isfile(match)
            )
            if matches:
                expanded.extend(matches)
                continue
        expanded.append(abs_path)
    return expanded

def expand_glob_inputs(
    project_dir: str,
    raw_inputs: list[str],
) -> list[tuple[str, list[str]]]:
    results = []
    for item in normalize_string_list(raw_inputs):
        abs_path = resolve_path(project_dir, item)
        if glob.has_magic(abs_path):
            matches = sorted(
                m for m in glob.glob(abs_path, recursive=True)
                if os.path.isfile(m)
            )
            if not matches:
                logger.warning("      [WARN] Glob pattern matched zero files: %s", item)
            results.append((item, matches))
        else:
            results.append((item, [abs_path]))
    return results


def flatten_glob_results(glob_results: list[tuple[str, list[str]]]) -> list[str]:
    return [p for _, paths in glob_results for p in paths]


def is_executable_available(cmd):
    if os.path.isabs(cmd) or cmd.startswith('.'):
        return os.path.isfile(cmd) and os.access(cmd, os.X_OK)
    return shutil.which(cmd) is not None

def scan_csv_export_anomalies(base_dir, paths):
    warnings = []
    for abs_path in expand_declared_paths(base_dir, paths):
        if not os.path.isfile(abs_path):
            continue
        if os.path.splitext(abs_path)[1].lower() != ".csv":
            continue
        try:
            with open(abs_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                header = next(reader, None)
        except (OSError, UnicodeDecodeError, csv.Error):
            continue

        if not header:
            continue

        normalized = [str(col).strip() for col in header]
        blank_headers = [col for col in normalized if not col]
        duplicate_headers = []
        seen = set()
        for col in normalized:
            if not col:
                continue
            if col in seen and col not in duplicate_headers:
                duplicate_headers.append(col)
            seen.add(col)

        if not blank_headers and not duplicate_headers:
            continue

        rel_path = os.path.relpath(abs_path, base_dir)
        warning = {
            "path": rel_path,
            "blank_headers": len(blank_headers),
            "duplicate_headers": duplicate_headers,
        }
        warnings.append(warning)

    if warnings:
        logger.warning("   🟠 [Input Export Anomaly] CSV header anomalies detected before analysis:")
        for warning in warnings[:10]:
            detail_parts = []
            if warning["duplicate_headers"]:
                detail_parts.append(
                    "duplicate headers: " + ", ".join(warning["duplicate_headers"])
                )
            if warning["blank_headers"]:
                detail_parts.append(f"blank headers: {warning['blank_headers']}")
            logger.warning("      - %s | %s", warning["path"], " | ".join(detail_parts))
        if len(warnings) > 10:
            logger.warning("      - ... %s more", len(warnings) - 10)

    return warnings

def prompt_numeric_selection(options, header="Select an Option"):
    """
    터미널에 목록을 출력하고 사용자로부터 번호를 입력받아 인덱스를 반환합니다.
    """
    print(f"\n🏛️  {header}")
    print("-" * 60)
    for i, opt in enumerate(options, 1):
        print(f" [{i}] {opt}")
    print("-" * 60)

    while True:
        choice = input(f"\nSelect number (1-{len(options)}) or 'q' to quit: ").strip().lower()
        if choice == 'q':
            print("👋 Project selection cancelled.")
            sys.exit(0)

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
            else:
                print(f"❌ Please enter a number between 1 and {len(options)}.")
        except ValueError:
            print("❌ Invalid input. Please enter a number.")

def verify_output_file(output_path):
    if not os.path.exists(output_path):
        return False, f"missing file: {output_path}"

    try:
        file_size = os.path.getsize(output_path)
    except OSError as e:
        return False, f"cannot stat output: {output_path} ({e})"

    if file_size <= 0:
        return False, f"empty file (0 byte): {output_path}"

    ext = os.path.splitext(output_path)[1].lower()
    try:
        with open(output_path, "rb") as f:
            header = f.read(2048)
    except OSError as e:
        return False, f"cannot read output: {output_path} ({e})"

    if ext == ".pdf" and not header.startswith(b"%PDF"):
        return False, f"invalid PDF header: {output_path}"
    if ext == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, f"invalid PNG header: {output_path}"
    if ext in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8"):
        return False, f"invalid JPEG header: {output_path}"
    if ext == ".svg":
        head_text = header.decode("utf-8", errors="ignore").lower()
        if "<svg" not in head_text:
            return False, f"invalid SVG content: {output_path}"

    return True, f"{output_path} ({file_size} bytes)"
