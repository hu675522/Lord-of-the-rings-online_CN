import struct
import unittest
from pathlib import Path

from lotro_zh.font_resource import BitmapFont, Glyph, alpha_texture, extend_font


class FontTests(unittest.TestCase):
    def test_current_format_metrics_come_before_codepoint_and_coordinates(self):
        raw = (struct.pack("<4I", 0x42000019, 18, 21, 1)
               + bytes((9, 11, 1, 1, 4)) + struct.pack("<3H", ord("H"), 19, 27)
               + struct.pack("<5I", 3, 3, 15, 0x41000109, 0x4100010a))
        parsed = BitmapFont.parse(raw)
        self.assertEqual(parsed.glyphs[0], Glyph(9, 11, 1, 1, 4, ord("H"), 19, 27))
        self.assertEqual(parsed.textures, (0x41000109, 0x4100010a))
        self.assertEqual(parsed.serialize(), raw)

    @unittest.skipUnless(Path(r"C:\Windows\Fonts\msyh.ttc").exists(), "Needs the local Windows CJK font")
    def test_extending_font_preserves_existing_metrics_and_every_original_pixel(self):
        from PIL import Image
        glyph = Glyph(9, 11, 1, 1, 4, ord("H"), 4, 4)
        original = BitmapFont(0x42000019, 18, 21, [glyph], struct.pack("<5I", 3, 3, 15, 0x41000109, 0))
        pixels = bytes(range(64)) * 32
        texture = struct.pack("<6I", 0x41000109, 13, 64, 32, 28, len(pixels)) + pixels
        raw, textures, stats = extend_font(original.serialize(), [texture], "中文", Path(r"C:\Windows\Fonts\msyh.ttc"))
        parsed = BitmapFont.parse(raw)
        self.assertEqual(next(g for g in parsed.glyphs if g.codepoint == ord("H")), glyph)
        self.assertEqual({g.codepoint for g in parsed.glyphs}, {ord("H"), ord("中"), ord("文")})
        image = alpha_texture(textures[0x41000109])
        self.assertEqual(image.crop((0, 0, 64, 32)).tobytes(), pixels)
        for g in parsed.glyphs:
            self.assertLessEqual(g.x + g.width, image.width)
            self.assertLessEqual(g.y + g.height, image.height)
        self.assertTrue(stats["original_pixels_preserved"])

    @unittest.skipUnless(Path(r"C:\Windows\Fonts\msyh.ttc").exists(), "Needs the local Windows CJK font")
    def test_full_han_coverage_can_widen_atlas_without_moving_original_pixels(self):
        glyph=Glyph(9,11,1,1,4,ord('H'),4,4)
        original=BitmapFont(0x42000019,18,21,[glyph],struct.pack('<5I',3,3,15,0x41000109,0))
        pixels=bytes(range(64))*32
        texture=struct.pack('<6I',0x41000109,13,64,32,28,len(pixels))+pixels
        _,textures,stats=extend_font(original.serialize(),[texture],
            ''.join(chr(0x4e00+i) for i in range(1600)),Path(r'C:\Windows\Fonts\msyh.ttc'))
        image=alpha_texture(textures[0x41000109])
        self.assertGreater(image.width,64)
        self.assertLessEqual(max(image.size),4096)
        self.assertEqual(image.crop((0,0,64,32)).tobytes(),pixels)


if __name__ == "__main__":
    unittest.main()
