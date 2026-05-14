import subprocess
import sys


def test_preset_help_lists_nature_surfur_target_format():
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "nature_surfur" in result.stdout
