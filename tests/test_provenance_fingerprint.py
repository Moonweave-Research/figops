import json
import os
import unittest
from pathlib import Path

from PIL import Image, PngImagePlugin

from hub_core.provenance import (
    _embed_pdf_fingerprint,
    _embed_png_fingerprint,
    _embed_svg_fingerprint,
    _fingerprint_payload_matches,
    _png_chunk,
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

    def test_png_embedding_is_idempotent_and_changed_payload_replaces_metadata(self):
        path = Path(self.test_dir) / "idempotent.png"
        Image.new("RGB", (8, 8), color="red").save(path)

        self.assertTrue(_embed_png_fingerprint(str(path), self.payload_str))
        before = (path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns)

        self.assertTrue(_embed_png_fingerprint(str(path), self.payload_str))
        self.assertEqual((path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns), before)

        changed = {**self.payload, "git": "changed-sha"}
        self.assertTrue(_embed_png_fingerprint(str(path), json.dumps(changed, separators=(",", ":"))))
        self.assertEqual(read_provenance_fingerprint(str(path)), changed)
        self.assertEqual(path.read_bytes().count(b"Research-Fingerprint"), 1)

    def test_fingerprint_payload_matching_preserves_json_value_types(self):
        self.assertFalse(_fingerprint_payload_matches('{"value":true}', '{"value":1}'))
        self.assertFalse(_fingerprint_payload_matches('{"value":1}', '{"value":1.0}'))
        self.assertTrue(_fingerprint_payload_matches('{"items":[1,"x"]}', '{ "items" : [1,"x"] }'))

    def test_png_changed_fingerprint_preserves_supported_metadata(self):
        path = Path(self.test_dir) / "metadata.png"
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("plain", "retained text")
        metadata.add_itxt("localized", "retained iTXt", lang="ko", tkey="Korean label")
        image = Image.new("RGB", (8, 8), color="red")
        image.save(
            path,
            pnginfo=metadata,
            dpi=(144, 144),
            icc_profile=b"test-icc-profile",
            exif=b"Exif\x00\x00test-exif",
        )
        image.close()

        self.assertTrue(_embed_png_fingerprint(str(path), self.payload_str))
        changed = {**self.payload, "git": "changed-sha"}
        self.assertTrue(_embed_png_fingerprint(str(path), json.dumps(changed, separators=(",", ":"))))

        with Image.open(path) as image:
            self.assertEqual(image.info["icc_profile"], b"test-icc-profile")
            self.assertEqual(image.info["exif"], b"Exif\x00\x00test-exif")
            self.assertEqual(image.info["plain"], "retained text")
            self.assertEqual(str(image.info["localized"]), "retained iTXt")
            self.assertEqual(image.info["localized"].lang, "ko")
            self.assertEqual(image.info["localized"].tkey, "Korean label")
            self.assertAlmostEqual(image.info["dpi"][0], 144, places=1)
            self.assertAlmostEqual(image.info["dpi"][1], 144, places=1)

    def test_png_duplicate_marker_with_matching_last_value_is_normalized(self):
        path = Path(self.test_dir) / "duplicate.png"
        Image.new("RGB", (8, 8), color="red").save(path)
        legacy = json.dumps({**self.payload, "git": "legacy-sha"}, separators=(",", ":"))
        self.assertTrue(_embed_png_fingerprint(str(path), legacy))

        original = path.read_bytes()
        idat_offset = original.index(b"IDAT") - 4
        duplicate = _png_chunk(b"tEXt", b"Research-Fingerprint\x00" + self.payload_str.encode("latin-1"))
        path.write_bytes(original[:idat_offset] + duplicate + original[idat_offset:])
        duplicate_state = path.read_bytes()

        self.assertTrue(_embed_png_fingerprint(str(path), self.payload_str))
        self.assertNotEqual(path.read_bytes(), duplicate_state)
        self.assertEqual(path.read_bytes().count(b"Research-Fingerprint"), 1)
        self.assertEqual(read_provenance_fingerprint(str(path)), self.payload)

    def test_png_bad_crc_fails_closed_without_mutating_even_when_marker_matches(self):
        path = Path(self.test_dir) / "bad-crc.png"
        Image.new("RGB", (8, 8), color="red").save(path)
        self.assertTrue(_embed_png_fingerprint(str(path), self.payload_str))

        corrupted = bytearray(path.read_bytes())
        idat_type_offset = corrupted.index(b"IDAT")
        idat_length = int.from_bytes(corrupted[idat_type_offset - 4 : idat_type_offset], "big")
        crc_offset = idat_type_offset + 4 + idat_length
        corrupted[crc_offset] ^= 0x01
        path.write_bytes(corrupted)
        before = path.read_bytes()

        self.assertFalse(_embed_png_fingerprint(str(path), self.payload_str))
        self.assertEqual(path.read_bytes(), before)

    def test_png_missing_ihdr_fails_closed_without_mutating(self):
        path = Path(self.test_dir) / "missing-ihdr.png"
        malformed = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IDAT", b"") + _png_chunk(b"IEND", b"")
        path.write_bytes(malformed)
        before = path.read_bytes()

        self.assertFalse(_embed_png_fingerprint(str(path), self.payload_str))
        self.assertEqual(path.read_bytes(), before)

    def test_png_idat_before_ihdr_fails_closed_without_mutating(self):
        path = Path(self.test_dir) / "idat-before-ihdr.png"
        ihdr = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        malformed = (
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IDAT", b"")
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IEND", b"")
        )
        path.write_bytes(malformed)
        before = path.read_bytes()

        self.assertFalse(_embed_png_fingerprint(str(path), self.payload_str))
        self.assertEqual(path.read_bytes(), before)

    def test_pdf_embedding_is_idempotent_when_pypdf_is_available(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest("pypdf is an optional dependency")

        path = Path(self.test_dir) / "idempotent.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with path.open("wb") as stream:
            writer.write(stream)

        self.assertTrue(_embed_pdf_fingerprint(str(path), self.payload_str))
        before = (path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns)

        self.assertTrue(_embed_pdf_fingerprint(str(path), self.payload_str))
        self.assertEqual((path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns), before)

        changed = {**self.payload, "git": "changed-sha"}
        self.assertTrue(_embed_pdf_fingerprint(str(path), json.dumps(changed, separators=(",", ":"))))
        self.assertEqual(read_provenance_fingerprint(str(path)), changed)

        from pypdf import PdfReader

        reader = PdfReader(str(path))
        self.assertEqual(sum(key == "/Research-Fingerprint" for key in reader.metadata), 1)

    def test_pdf_changed_fingerprint_preserves_document_metadata_and_repairs_hashes(self):
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            self.skipTest("pypdf is an optional dependency")

        path = Path(self.test_dir) / "metadata.pdf"
        legacy = {**self.payload, "git": "legacy-sha"}
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_metadata(
            {
                "/Title": "Preserved title",
                "/Author": "Preserved author",
                "/Research-Fingerprint": json.dumps(legacy, separators=(",", ":")),
                "/Research-Config-Hash": "legacy-only",
            }
        )
        with path.open("wb") as stream:
            writer.write(stream)

        changed = {**self.payload, "config": "fresh-config", "env": "fresh-env", "git": "changed-sha"}
        self.assertTrue(_embed_pdf_fingerprint(str(path), json.dumps(changed, separators=(",", ":"))))
        self.assertEqual(read_provenance_fingerprint(str(path)), changed)

        metadata = PdfReader(str(path)).metadata
        self.assertEqual(metadata["/Title"], "Preserved title")
        self.assertEqual(metadata["/Author"], "Preserved author")
        self.assertEqual(metadata["/Research-Config-Hash"], "fresh-config")
        self.assertEqual(metadata["/Research-Env-Hash"], "fresh-env")

    def test_pdf_matching_fingerprint_with_incomplete_companions_is_repaired(self):
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            self.skipTest("pypdf is an optional dependency")

        path = Path(self.test_dir) / "incomplete-metadata.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_metadata(
            {
                "/Research-Fingerprint": self.payload_str,
                "/Research-Config-Hash": self.payload["config"],
                "/Research-Env-Hash": "wrong-env",
            }
        )
        with path.open("wb") as stream:
            writer.write(stream)

        self.assertTrue(_embed_pdf_fingerprint(str(path), self.payload_str))
        metadata = PdfReader(str(path)).metadata
        self.assertEqual(metadata["/Research-Config-Hash"], self.payload["config"])
        self.assertEqual(metadata["/Research-Env-Hash"], self.payload["env"])

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

    def test_svg_embedding_is_idempotent_and_changed_payload_replaces_comment(self):
        path = Path(self.test_dir) / "idempotent.svg"
        path.write_text('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")

        self.assertTrue(_embed_svg_fingerprint(str(path), self.payload_str))
        before = (path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns)

        self.assertTrue(_embed_svg_fingerprint(str(path), self.payload_str))
        self.assertEqual((path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns), before)

        changed = {**self.payload, "git": "changed-sha"}
        self.assertTrue(_embed_svg_fingerprint(str(path), json.dumps(changed, separators=(",", ":"))))
        self.assertEqual(read_provenance_fingerprint(str(path)), changed)
        self.assertEqual(path.read_text(encoding="utf-8").count("<!-- Research-Fingerprint:"), 1)

    def test_svg_readback_finds_marker_after_4kb_and_upserts_multiple_markers(self):
        path = Path(self.test_dir) / "late-and-duplicate.svg"
        legacy = {**self.payload, "git": "legacy-sha"}
        legacy_comment = json.dumps(legacy, separators=(",", ":"))
        path.write_text(
            "<svg>" + (" " * 5000) + f"<!-- Research-Fingerprint: {legacy_comment} -->"
            f"<!-- Research-Fingerprint: {self.payload_str} --></svg>",
            encoding="utf-8",
        )

        self.assertEqual(read_provenance_fingerprint(str(path)), legacy)
        changed = {**self.payload, "git": "changed-sha"}
        self.assertTrue(_embed_svg_fingerprint(str(path), json.dumps(changed, separators=(",", ":"))))
        self.assertEqual(read_provenance_fingerprint(str(path)), changed)
        self.assertEqual(path.read_text(encoding="utf-8").count("<!-- Research-Fingerprint:"), 1)

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
