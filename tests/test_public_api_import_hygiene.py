import ast
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


if __name__ == "__main__":
    unittest.main()
