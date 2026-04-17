
import json
import os
import unittest

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
            "dvc": "up_to_date",
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


if __name__ == "__main__":
    unittest.main()
