import subprocess
import sys

from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT


def test_preset_help_lists_internal_project_target_format():
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert INTERNAL_STYLE_TARGET_FORMAT in result.stdout
