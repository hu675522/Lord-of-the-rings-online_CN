from io import BytesIO
import struct
import unittest

from lotro_zh.dat_reader import DatError, DatReader, Entry


class OpaqueResourceTests(unittest.TestCase):
    def test_opaque_comparison_does_not_disable_default_id_validation(self):
        payload = b'opaqueUI'
        reader = DatReader.__new__(DatReader)
        reader.stream = BytesIO(struct.pack('<II', 0, 0) + payload)
        reader.length = len(reader.stream.getvalue())
        entry = Entry(0x20000001, 0, len(payload), 8 + len(payload), 2)
        with self.assertRaises(DatError):
            reader.content(entry)
        self.assertEqual(reader.content(entry, validate_identifier=False), payload)
        with self.assertRaises(DatError):
            reader.content(entry)
