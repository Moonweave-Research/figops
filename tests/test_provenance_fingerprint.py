import json
import os
import unittest
from pathlib import Path

from PIL import Image

from hub_core.provenance import (
    _embed_pdf_fingerprint,
    _embed_png_fingerprint,
    _embed_svg_fingerprint,
    build_fingerprint_payload,
    hash_csv_file,
    read_provenance_fingerprint,
)


class TestProvenanceFingerprint(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/tmp_provenance"
        os.makedirs(self.test_dir, exist_ok=True)
        self.payload = {
            "project": "TestProject",
            "config": "c0ffee",
            "env": "b007",
            "git": "git-sha",
            "ts": "2026-03-09T00:00:00",
            "generator": "TestGenerator",
        }
        self.payload_str = json.dumps(self.payload, separators=(",", ":"))

    def tearDown(self):
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_png_embedding_and_readback(self):
        path = os.path.join(self.test_dir, "test.png")
        img = Image.new("RGB", (100, 100), color="red")
        img.save(path)
        img.close()

        success = _embed_png_fingerprint(path, self.payload_str)
        self.assertTrue(success)

        readback = read_provenance_fingerprint(path)
        self.assertEqual(readback, self.payload)

    def test_pdf_graceful_degradation(self):
        # We know pypdf is NOT installed from previous check
        path = os.path.join(self.test_dir, "test.pdf")
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4\n%EOF")

        success = _embed_pdf_fingerprint(path, self.payload_str)
        self.assertFalse(success)

    def test_svg_embedding_and_readback(self):
        path = os.path.join(self.test_dir, "test.svg")
        svg_content = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<svg height="100" width="100">'
            '<circle cx="50" cy="50" r="40" stroke="black"'
            ' stroke-width="3" fill="red" /></svg>'
        )
        with open(path, "w") as f:
            f.write(svg_content)

        success = _embed_svg_fingerprint(path, self.payload_str)
        self.assertTrue(success)

        readback = read_provenance_fingerprint(path)
        self.assertEqual(readback, self.payload)

    def test_hash_csv_file(self):
        path = os.path.join(self.test_dir, "data.csv")
        with open(path, "w") as f:
            f.write("x,y\n1,2\n3,4\n")

        result = hash_csv_file(path)
        self.assertEqual(len(result), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_hash_csv_file_missing(self):
        result = hash_csv_file(os.path.join(self.test_dir, "nonexistent.csv"))
        self.assertEqual(result, "")

    def test_fingerprint_includes_csv_hash(self):
        path = os.path.join(self.test_dir, "data.csv")
        with open(path, "w") as f:
            f.write("x,y\n1,2\n3,4\n")

        csv_hash = hash_csv_file(path)
        fingerprint = build_fingerprint_payload(
            project_name="TestProject",
            config_hash="abc123",
            environment_hash="def456",
            git_commit="abcdef0",
            timestamp="2026-01-01T00:00:00",
            data_hashes={"data.csv": csv_hash},
        )
        self.assertIn("data", fingerprint)
        self.assertEqual(fingerprint["data"]["data.csv"], csv_hash)
        self.assertEqual(len(csv_hash), 16)

    def test_glob_hashes_use_project_relative_paths_and_file_bytes(self):
        from hub_core.provenance import _hash_input_files

        first = Path(self.test_dir) / "first" / "same.csv"
        second = Path(self.test_dir) / "second" / "same.csv"
        first.parent.mkdir()
        second.parent.mkdir()
        first.write_text("x\n1\n", encoding="utf-8")
        second.write_text("x\n2\n", encoding="utf-8")

        hashes = _hash_input_files(self.test_dir, ["**/*.csv"])

        self.assertEqual(set(hashes), {"first/same.csv", "second/same.csv"})
        self.assertNotEqual(hashes["first/same.csv"], hashes["second/same.csv"])

    def test_directory_hash_changes_when_bytes_change_with_preserved_mtime(self):
        from hub_core.provenance import _hash_input_files

        data_dir = Path(self.test_dir) / "data"
        data_dir.mkdir()
        sample = data_dir / "sample.csv"
        sample.write_text("x\n1\n", encoding="utf-8")
        original_stat = sample.stat()
        before = _hash_input_files(self.test_dir, ["data"])

        sample.write_text("x\n9\n", encoding="utf-8")
        os.utime(sample, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        after = _hash_input_files(self.test_dir, ["data"])

        self.assertNotEqual(before, after)

    def test_embed_figures_preserves_declared_input_patterns(self):
        from hub_core.provenance import embed_figures_fingerprint

        project = Path(self.test_dir)
        (project / "data").mkdir()
        (project / "data" / "sample.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        output = project / "results" / "figures" / "figure.png"
        output.parent.mkdir(parents=True)
        Image.new("RGB", (8, 8), color="white").save(output)
        config = {
            "project": {"name": "PatternProject"},
            "figures": [
                {
                    "output": "results/figures/figure.png",
                    "inputs": ["data/**/*.csv"],
                    "script": "plot.py",
                }
            ],
        }

        embedded = embed_figures_fingerprint(
            str(project),
            config,
            config_hash="config",
            environment_hash="environment",
            git_commit="commit",
            timestamp="1970-01-01T00:00:01+00:00",
        )

        self.assertEqual(embedded, 1)
        fingerprint = read_provenance_fingerprint(str(output))
        self.assertEqual(fingerprint["input_patterns"], ["data/**/*.csv"])
        self.assertIn("data/sample.csv", fingerprint["data"])


if __name__ == "__main__":
    unittest.main()
