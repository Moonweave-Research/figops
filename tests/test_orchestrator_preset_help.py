import subprocess
import sys


def test_preset_help_lists_public_target_formats_only():
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "nature, science, default, acs, rsc, elsevier, wiley, cell" in result.stdout
    assert "presentation_private" not in result.stdout
