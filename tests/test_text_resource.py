import struct
import unittest

from lotro_zh.text_resource import Cursor, Fragment, TextFormatError, TextResource, encode_text, variable


class TextResourceTests(unittest.TestCase):
    def test_variable_boundaries(self):
        for length in (0, 1, 127, 128, 255, 256, 32767):
            self.assertEqual(Cursor(variable(length)).variable(), length)
        for length in (-1, 32768):
            with self.assertRaises(TextFormatError):
                variable(length)

    def test_utf16_counts_code_units_including_supplementary_character(self):
        self.assertEqual(Cursor(encode_text("中文🙂")).text(), "中文🙂")
        self.assertEqual(encode_text("中文🙂")[0], 4)

    def test_roundtrip_preserves_arguments_unknown_header_and_tail(self):
        resource = TextResource(0x25000001, b"\x01\x02\x03\x04\x05", [
            Fragment(123, ["Hello ", ", collect ", " items."], [b"\x01\0\0\0", b"\x05\0\0\0"], [["one", "many"]])
        ], b"\x77\x88")
        raw = resource.serialize()
        parsed = TextResource.parse(raw)
        self.assertEqual(parsed.serialize(), raw)
        parsed.fragments[0].pieces = ["你好，", "，收集 ", " 件物品。"]
        changed = TextResource.parse(parsed.serialize())
        self.assertEqual(changed.fragments[0].arg_refs, resource.fragments[0].arg_refs)
        self.assertEqual(changed.fragments[0].arg_strings, resource.fragments[0].arg_strings)
        self.assertEqual(changed.unknown, resource.unknown)
        self.assertEqual(changed.trailing, resource.trailing)

    def test_truncated_resource_rejected(self):
        with self.assertRaises(TextFormatError):
            TextResource.parse(struct.pack("<I", 0x25000001))

    def test_other_resource_type_rejected(self):
        with self.assertRaises(TextFormatError):
            TextResource.parse(struct.pack("<I", 0x42000001) + bytes(20))


if __name__ == "__main__":
    unittest.main()
