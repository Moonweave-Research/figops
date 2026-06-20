import os
import shutil
import subprocess
import sys

from .ui_utils import ui_panel
from .utils import get_hub_path, get_research_root

REQUIRED_PYTHON = (3, 10)

def check_python():
    current = sys.version_info[:2]
    if current < REQUIRED_PYTHON:
        return False, f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ required (found {current[0]}.{current[1]})"
    return True, f"Python {current[0]}.{current[1]} OK"

def check_r():
    rscript = shutil.which("Rscript")
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

def run_preflight_check(exit_on_failure=True):
    py_ok, py_msg = check_python()
    r_ok, r_msg = check_r()
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
                "   └─ Guide: Install R from https://cran.r-project.org/ or 'brew install r'.\n\n"
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
