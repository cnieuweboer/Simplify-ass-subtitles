"""Font usability checks without requiring strictly conforming optional tables."""

import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

spec = importlib.util.spec_from_file_location(
    "sync_fonts", Path(__file__).resolve().parents[1] / "sync_fonts.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def make_font(path, extra=None):
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    glyphs = {}
    for name in (".notdef", "A"):
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((300, 700))
        pen.lineTo((600, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in glyphs})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Test Font", "styleName": "Regular",
                            "fullName": "Test Font Regular", "psName": "TestFont-Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                     usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    if extra:
        from fontTools.ttLib.tables.DefaultTable import DefaultTable
        for tag, data in extra.items():
            table = DefaultTable(tag)
            table.data = data
            builder.font[tag] = table
    builder.save(path)


class FontValidationChecks(unittest.TestCase):
    def test_nonconforming_optional_tables_keep_readable_font_and_source_bytes(self):
        # Extra smoothing data and inconsistent bitmap-size ranges reproduce
        # the two uploaded fonts' failure classes without distributing them.
        tables = {
            "gasp": struct.pack(">HHHHI", 0, 1, 65535, 3, 0),
            "VDMX": struct.pack(">HHHBBBBHHBBHhh", 0, 1, 1, 0, 1, 1, 1,
                                12, 1, 9, 10, 10, 8, -2),
        }
        with tempfile.TemporaryDirectory() as folder:
            for tag, data in tables.items():
                with self.subTest(table=tag):
                    path = Path(folder) / (tag + ".ttf")
                    make_font(path, {tag: data})
                    original = path.read_bytes()
                    with TTFont(path, lazy=True) as strict:
                        with self.assertRaises(Exception):
                            strict.ensureDecompiled()
                    faces = sync.font_faces(path)
                    self.assertEqual(len(faces), 1)
                    self.assertTrue(sync.face_matches(faces[0], ("test font", 400, False)))
                    self.assertEqual(path.read_bytes(), original)

    def test_bad_required_tables_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for tag in ("name", "cmap", "head", "hmtx", "glyf"):
                with self.subTest(table=tag):
                    path = Path(folder) / (tag + ".ttf")
                    make_font(path)
                    data = bytearray(path.read_bytes())
                    for offset in range(12, 12 + 16 * struct.unpack_from(">H", data, 4)[0], 16):
                        if data[offset:offset + 4] == tag.encode("ascii"):
                            # Truncate the table in the directory, leaving all
                            # unrelated table offsets and data intact.
                            struct.pack_into(">I", data, offset + 12, 1)
                            break
                    else:
                        self.fail("Fixture table not found: " + tag)
                    path.write_bytes(data)
                    with self.assertRaises(Exception):
                        sync.font_faces(path)

    def test_text_mislabeled_as_font_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fake.ttf"
            path.write_text("This is not a font.")
            with self.assertRaises(Exception):
                sync.font_faces(path)

    def test_collection_checks_every_face(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_font(root / "one.ttf")
            make_font(root / "two.ttf")
            collection = TTCollection()
            collection.fonts = [TTFont(root / "one.ttf"), TTFont(root / "two.ttf")]
            try:
                collection.save(root / "both.ttc")
            finally:
                collection.close()
            self.assertEqual(len(sync.font_faces(root / "both.ttc")), 2)

    def test_optional_table_issue_does_not_hide_local_font(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "font.ttf"
            make_font(path, {"gasp": struct.pack(">HHHHI", 0, 1, 65535, 3, 0)})
            digest = hashlib.sha256(path.read_bytes()).digest()
            catalog = sync.local_font_catalog(root, {})
            self.assertEqual([item["path"] for item in catalog], [path])
            self.assertIn("Test Font", catalog[0]["names"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)


if __name__ == "__main__":
    unittest.main()
