import os
import shutil
import subprocess
import sys
from collections.abc import Mapping

from .config_parser import normalize_lang
from .process_runner_commands import resolve_runner
from .ui_utils import ui_panel
from .utils import get_hub_path, get_research_root

REQUIRED_PYTHON = (3, 10)

def check_python():
    current = sys.version_info[:2]
    if current < REQUIRED_PYTHON:
        return False, f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ required (found {current[0]}.{current[1]})"
    return True, f"Python {current[0]}.{current[1]} OK"

def check_r(rscript: str = "Rscript"):
    rscript = shutil.which(rscript)
    if not rscript:
        return False, "R (Rscript) not found in PATH. Please install R to run analysis steps."

    try:
        res = subprocess.run([rscript, "--version"], capture_output=True, text=True)
        version = res.stderr.strip() or res.stdout.strip()
        return True, f"R found: {version}"
    except Exception:
        return False, "R found but failed to execute 'Rscript --version'."

def check_env_vars():
    """
    환경 변수가 없더라도 자동 추론이 가능하면 통과시킵니다.
    대신 경고 메시지를 반환합니다.
    """
    hub_path = get_hub_path()
    root_path = get_research_root()

    missing = []
    if not os.environ.get("PROJECT_ROOT"):
        missing.append("PROJECT_ROOT")
    if not os.environ.get("RESEARCH_HUB_PATH"):
        missing.append("RESEARCH_HUB_PATH")

    if missing:
        msg = f"Missing env vars: {', '.join(missing)} (Using auto-inferred paths)"
        # 경로가 유효한지 최종 확인
        if os.path.exists(hub_path) and os.path.exists(root_path):
            return True, msg, True  # Success, Message, is_warning=True
        return False, f"Missing env vars and auto-inference failed: {', '.join(missing)}", False

    return True, "Environment variables OK", False

def required_r_runners(config: Mapping[str, object], step: str) -> tuple[str, ...]:
    """Return the distinct R runners needed by the selected pipeline step."""
    selected_sections = _selected_sections(step)
    runners: list[str] = []
    for section_name, default_language in selected_sections:
        entries = _section_entries(config, section_name)
        for entry in entries:
            if section_name == "analysis" and entry.get("domain_helper"):
                continue
            language = _entry_language(entry, default_language)
            if language != "r":
                continue
            runner = resolve_runner(language, entry, config)
            if isinstance(runner, str) and runner not in runners:
                runners.append(runner)
    return tuple(runners)


def run_preflight_check(exit_on_failure=True, *, rscript_commands: tuple[str, ...] | None = None):
    py_ok, py_msg = check_python()
    commands = ("Rscript",) if rscript_commands is None else rscript_commands
    r_results = [check_r(command) for command in commands]
    r_ok = all(result[0] for result in r_results)
    r_msg = "; ".join(result[1] for result in r_results) or "R check not required for selected steps."
    env_ok, env_msg, is_env_warning = check_env_vars()

    all_ok = py_ok and r_ok and env_ok

    if not all_ok or is_env_warning:
        style = "yellow" if all_ok else "red"
        title = "Health Check (Warning)" if all_ok else "Health Check (Failed)"
        status_icon = "⚠️" if all_ok else "🚨"

        msg = f"{status_icon} [bold {style}]{title}[/bold {style}]\n\n"

        if not py_ok:
            msg += (
                f"❌ [yellow]{py_msg}[/yellow]\n"
                "   └─ Guide: Update Python via 'uv python install' or your system manager.\n\n"
            )
        if not r_ok:
            msg += (
                f"❌ [yellow]{r_msg}[/yellow]\n"
                "   └─ Guide: Install R for projects that declare `lang: R`, ensure Rscript is on PATH, "
                "then rerun the check.\n\n"
            )
        if is_env_warning:
            msg += (
                f"⚠️  [blue]{env_msg}[/blue]\n"
                f"   └─ Hub: {get_hub_path()}\n"
                f"   └─ Root: {get_research_root()}\n"
                "   └─ Guide: Set variables in .env for better stability.\n"
            )
        elif not env_ok:
            msg += f"❌ [red]{env_msg}[/red]\n   └─ Guide: Set these in your .env or shell profile.\n"

        ui_panel(msg, title="Health Check", style=style)

        if not all_ok and exit_on_failure:
            sys.exit(1)

    return all_ok


def _selected_sections(step: str) -> tuple[tuple[str, str], ...]:
    if step == "analysis":
        return (("analysis", "r"),)
    if step == "plot":
        return (("figures", "python"),)
    if step == "diagrams":
        return (("diagrams", "python"),)
    if step == "all":
        return (("analysis", "r"), ("figures", "python"), ("diagrams", "python"))
    return ()


def _section_entries(config: Mapping[str, object], section_name: str) -> list[Mapping[str, object]]:
    if section_name == "analysis":
        pipeline = config.get("pipeline")
        raw_entries = pipeline.get("analysis") if isinstance(pipeline, Mapping) else None
    else:
        raw_entries = config.get(section_name)
    if not isinstance(raw_entries, list):
        return []
    return [entry for entry in raw_entries if isinstance(entry, Mapping)]


def _entry_language(entry: Mapping[str, object], default_language: str) -> str:
    raw_language = entry.get("lang")
    if raw_language is None:
        script = entry.get("script")
        if isinstance(script, str) and script.lower().endswith(".r"):
            return "r"
        return default_language
    return normalize_lang(raw_language)
