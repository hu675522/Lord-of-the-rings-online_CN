import json
import sqlite3
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from lotro_zh.dat_reader import DatReader, DatError, Entry, text_candidates
from lotro_zh.store import Store, normalize

ROOT = Path(__file__).resolve().parents[1]


class DatTests(unittest.TestCase):
    def fixture(self, path, payload, compressed=False):
        did = 0x25000001
        stored = struct.pack("<I", len(payload)) + zlib.compress(payload) if compressed else payload
        data = bytearray(4096)
        for offset, value in [(0x101, 0x4c50), (0x140, 0x5442), (0x144, 256), (0x160, 2048)]:
            struct.pack_into("<I", data, offset, value)
        struct.pack_into("<I", data, 2048 + 504, 1)
        struct.pack_into("<8I", data, 2048 + 508, int(compressed), did, 3072, len(stored), 0, 1, 512, 0)
        data[3080:3080 + len(stored)] = stored
        path.write_bytes(data)

    def test_reads_text_and_keeps_archive_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.dat"
            payload = struct.pack("<I", 0x25000001) + b"\x01" + "Prologue: Finding Amdir".encode("utf-16-le")
            for compressed in (False, True):
                self.fixture(path, payload, compressed)
                before = path.read_bytes()
                with DatReader(path) as reader:
                    entry, = reader.entries()
                    self.assertEqual(reader.content(entry), payload)
                    self.assertIn("Prologue: Finding Amdir", list(text_candidates(payload)))
                self.assertEqual(path.read_bytes(), before)

    def test_rejects_corrupt_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.dat"
            self.fixture(path, struct.pack("<I", 0x25000001))
            with DatReader(path) as reader:
                with self.assertRaises(DatError):
                    reader.content(Entry(0x25000001, 999999, 10, 256, 0))

    def test_rejects_directory_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.dat"
            self.fixture(path, struct.pack("<I", 0x25000001))
            data = bytearray(path.read_bytes())
            struct.pack_into("<II", data, 2056, 256, 2048)
            path.write_bytes(data)
            with DatReader(path) as reader:
                with self.assertRaises(DatError):
                    list(reader.entries())


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name), ROOT / "samples.json")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_sample_exact_lookup(self):
        result = self.store.search("Prologue: Finding Amdir")
        self.assertTrue(result["translation"]["zh"])
        self.assertEqual(result["items"][0]["match"], "exact")

    def test_missing_translation_is_not_invented(self):
        result = self.store.search("A quest which does not exist")
        self.assertEqual(result["translation"]["origin"], "missing")
        self.assertEqual(result["translation"]["zh"], "")

    def test_user_revision_survives_restart(self):
        self.store.save("Prologue: Finding Amdir", "我的修订")
        self.store.close()
        self.store = Store(Path(self.temp.name), ROOT / "samples.json")
        self.assertEqual(self.store.lookup("Prologue: Finding Amdir")["zh"], "我的修订")
        self.assertEqual(self.store.lookup("Prologue: Finding Amdir")["origin"], "user")

    def test_displayed_and_escaped_newlines_match(self):
        self.assertEqual(normalize("Hello\\n\\nMiddle-earth"), normalize("Hello\n\nMiddle-earth"))

    def test_fuzzy_candidate_does_not_overwrite_ocr(self):
        original = "Hooded Cloak of Shadows[s]"
        self.store.db.execute("INSERT INTO texts(resource_id,segment,text,norm) VALUES(?,?,?,?)", (0x25003524, 0, original, normalize(original)))
        self.store.db.execute("INSERT INTO texts_fts(texts_fts) VALUES('rebuild')")
        self.store.db.commit()
        result = self.store.search("Hooded CIoak of Shadows[s]")
        self.assertEqual(result["items"][0]["text"], original)
        self.assertEqual(result["translation"]["zh"], "")

    def test_multiline_ocr_title_is_high_priority_but_not_auto_applied(self):
        title = "Prologue: Finding Amdir"
        self.store.db.execute("INSERT INTO texts(resource_id,segment,text,norm) VALUES(?,?,?,?)", (0x2500020b, 0, title, normalize(title)))
        self.store.db.execute("INSERT INTO texts_fts(texts_fts) VALUES('rebuild')")
        self.store.db.commit()
        result = self.store.search(title + "\nA different line on the screen")
        self.assertEqual(result["items"][0]["text"], title)
        self.assertEqual(result["items"][0]["match"], "line")
        self.assertEqual(result["translation"]["zh"], "")

    def test_failed_rebuild_keeps_old_index_and_user_translation(self):
        self.store.save("My English", "我的中文")
        with self.assertRaises(FileNotFoundError):
            self.store.build(str(Path(self.temp.name) / "missing"))
        self.assertEqual(self.store.lookup("My English")["zh"], "我的中文")

    def test_keyword_syntax_is_treated_as_text(self):
        self.store.search('Amdir " OR * [ ] :')


if __name__ == "__main__":
    unittest.main()
