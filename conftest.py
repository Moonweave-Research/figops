"""Pytest root conftest — anchors rootdir and ensures hub_core is importable."""
import sys
from pathlib import Path

# Guarantee the hub root is on sys.path regardless of how pytest is invoked.
_HUB_ROOT = Path(__file__).resolve().parent
if str(_HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(_HUB_ROOT))
