import ast
import subprocess
import sys
import unittest
from pathlib import Path


class PublicApiImportHygieneTest(unittest.TestCase):
    def test_top_level_init_does_not_swallow_import_errors(self):
        tree = ast.parse(Path("__init__.py").read_text(encoding="utf-8"))

        broad_import_handlers = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or node.type is None:
                continue
            if isinstance(node.type, ast.Name) and node.type.id == "ImportError":
                broad_import_handlers.append(node)

        self.assertEqual(broad_import_handlers, [])

    def test_hub_core_facade_import_is_lightweight(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import hub_core; "
                    "assert 'hub_core.data_regression' not in sys.modules; "
                    "assert 'hub_core.process_runner' not in sys.modules; "
                    "assert 'hub_core.visual_regression' not in sys.modules; "
                    "assert 'pandas' not in sys.modules; "
                    "assert 'matplotlib' not in sys.modules"
                ),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

    def test_hub_core_mcp_facade_import_is_lightweight(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import hub_core.mcp; "
                    "assert 'hub_core.mcp.schemas' not in sys.modules; "
                    "assert 'hub_core.mcp.server' not in sys.modules; "
                    "assert 'themes.style_profiles' not in sys.modules; "
                    "assert 'cycler' not in sys.modules"
                ),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

    def test_doctor_import_does_not_load_heavy_mcp_schema_surface(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import hub_core.doctor; "
                    "assert 'hub_core.mcp.schemas' not in sys.modules; "
                    "assert 'hub_core.mcp.server' not in sys.modules; "
                    "assert 'themes.style_profiles' not in sys.modules; "
                    "assert 'cycler' not in sys.modules"
                ),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == "__main__":
    unittest.main()
