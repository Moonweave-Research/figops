import subprocess
import sys

from hub_core.config_parser import PUBLIC_TARGET_FORMATS


def test_preset_help_lists_public_target_formats():
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert all(target_format in result.stdout for target_format in PUBLIC_TARGET_FORMATS)
