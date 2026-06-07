import csv
import glob
import hashlib
import os
import shutil
import sys
import time

PREFETCH_ATTEMPTS = 3
PREFETCH_RETRY_DELAYS = (0.25, 1.0)


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
                print(f"      [WARN] Glob pattern matched zero files: {item}")
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

def ensure_local_files(paths):
    """
    가상 파일(Google Drive File Stream)을 강제로 한 번 읽어서 로컬 다운로드를 유도합니다.
    디렉토리가 주어지면 내부의 모든 파일을 재귀적으로 처리하며, 실시간 진행률을 표시합니다.
    """
    if not paths:
        return

    targets = []
    for p in expand_declared_paths(os.getcwd(), paths):
        if os.path.isfile(p):
            targets.append(p)
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    targets.append(os.path.join(root, f))

    total = len(targets)
    if total == 0:
        return

    print(f"   📡 [Prefetch] Ensuring {total} files are local (Google Drive Sync)...")
    success_count = 0
    fail_count = 0
    failed_targets = []

    for i, p in enumerate(targets, 1):
        filename = os.path.basename(p)
        # 긴 파일명 생략 처리
        display_name = (filename[:30] + '..') if len(filename) > 32 else filename

        # 실시간 진행률 출력 (동일 라인 업데이트는 터미널 환경에 따라 다르므로 줄바꿈 없이 출력 시도)
        sys.stdout.write(f"\r      └─ Progress: [{i}/{total}] {display_name}   ")
        sys.stdout.flush()

        last_error = None
        attempts_used = 0
        for attempt in range(PREFETCH_ATTEMPTS):
            attempts_used = attempt + 1
            try:
                # 첫 1바이트 읽기로 다운로드 유도
                with open(p, "rb") as f:
                    f.read(1)
                success_count += 1
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < len(PREFETCH_RETRY_DELAYS):
                    time.sleep(PREFETCH_RETRY_DELAYS[attempt])

        if last_error is not None:
            fail_count += 1
            failed_targets.append((display_name, type(last_error).__name__, attempts_used))

    sys.stdout.write("\n") # 진행률 줄바꿈

    if fail_count > 0:
        failed_preview = ", ".join(
            f"{name} ({error_name}, attempts={attempts})"
            for name, error_name, attempts in failed_targets[:3]
        )
        print(
            f"      ⚠️  Prefetch incomplete: {success_count}/{total} ready, "
            f"{fail_count} timed out or unavailable."
        )
        if failed_preview:
            print(f"         unresolved: {failed_preview}")
        print("         pipeline will continue and let the downstream step decide.")
    else:
        print(f"      ✅ All {success_count} files are ready locally.")


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
        print("   🟠 [Input Export Anomaly] CSV header anomalies detected before analysis:")
        for warning in warnings[:10]:
            detail_parts = []
            if warning["duplicate_headers"]:
                detail_parts.append(
                    "duplicate headers: " + ", ".join(warning["duplicate_headers"])
                )
            if warning["blank_headers"]:
                detail_parts.append(f"blank headers: {warning['blank_headers']}")
            print(f"      - {warning['path']} | " + " | ".join(detail_parts))
        if len(warnings) > 10:
            print(f"      - ... {len(warnings) - 10} more")

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
