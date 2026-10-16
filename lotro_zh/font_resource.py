"""Extend the current client's bitmap fonts without redrawing Latin glyphs.

The current format was checked against the local atlas pixels. A glyph is
width/height/left bearing/right bearing/y offset, followed by codepoint/x/y.
The historic Mojo converter's field labels do not match this client's layout.
"""
import math
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Glyph:
    width: int
    height: int
    left: int
    right: int
    top: int
    codepoint: int
    x: int
    y: int

    def serialize(self):
        return struct.pack("<BBbbBHHH", self.width, self.height, self.left, self.right,
                           self.top, self.codepoint, self.x, self.y)


@dataclass
class BitmapFont:
    identifier: int
    height: int
    line_height: int
    glyphs: list[Glyph]
    tail: bytes

    @classmethod
    def parse(cls, raw):
        if len(raw) < 36:
            raise ValueError("字体资源过短")
        did, height, line_height, count = struct.unpack_from("<4I", raw)
        if did >> 24 != 0x42 or len(raw) != 36 + count * 11:
            raise ValueError("不支持的字体资源布局")
        glyphs = [Glyph(*struct.unpack_from("<BBbbBHHH", raw, 16 + i * 11)) for i in range(count)]
        return cls(did, height, line_height, glyphs, raw[16 + count * 11:])

    @property
    def textures(self):
        return struct.unpack_from("<2I", self.tail, 12)

    def serialize(self):
        if len(self.tail) != 20:
            raise ValueError("字体尾部结构改变")
        return (struct.pack("<4I", self.identifier, self.height, self.line_height, len(self.glyphs))
                + b"".join(g.serialize() for g in self.glyphs) + self.tail)


def alpha_texture(raw):
    from PIL import Image
    if len(raw) < 24:
        raise ValueError("纹理资源过短")
    did, flags, width, height, fmt, size = struct.unpack_from("<6I", raw)
    if did >> 24 != 0x41 or fmt != 28 or size != width * height or len(raw) != size + 24:
        raise ValueError("仅支持当前字体使用的 A8 纹理")
    return Image.frombytes("L", (width, height), raw[24:])


def encode_alpha_texture(original, image):
    did, flags, _, _, fmt, _ = struct.unpack_from("<6I", original)
    if image.mode != "L" or max(image.size) > 4096:
        raise ValueError("字体纹理格式或尺寸不支持")
    pixels = image.tobytes()
    return struct.pack("<6I", did, flags, image.width, image.height, fmt, len(pixels)) + pixels


def extend_font(font_raw, texture_raws, characters, ttf_path):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    font = BitmapFont.parse(font_raw)
    if font.serialize() != font_raw:
        raise ValueError("原字体无修改往返不一致")
    existing = {g.codepoint for g in font.glyphs}
    additions = sorted({ord(c) for c in characters} - existing)
    if any(c > 0xffff for c in additions):
        raise ValueError("验证字库只支持 BMP 码位")
    if not additions:
        return font_raw, {}, {"new_glyphs": 0}
    images = [alpha_texture(raw) for raw in texture_raws]
    if not images or any(image.size != images[0].size for image in images):
        raise ValueError("填充与阴影纹理尺寸不一致")
    old_width, old_height = images[0].size
    width=old_width
    reference = next((g for g in font.glyphs if g.codepoint == ord("H")), None)
    if reference is None:
        raise ValueError("找不到基线参考字形 H")
    baseline = reference.top + reference.height
    size = max(8, round(reference.height * 1.2))
    # The two font-header heights differ across font families. Fit inside the
    # existing height envelope rather than assuming one field is always line
    # height (the tiny console family has a smaller second field).
    vertical_limit = max(font.height, font.line_height, baseline + 2)
    while size >= 6:
        han = ImageFont.truetype(str(ttf_path), size)
        bounds = [han.getbbox(chr(code), anchor="ls") for code in additions]
        if all(max(1, b[3] - b[1]) + max(0, baseline + b[1]) <= vertical_limit for b in bounds):
            break
        size -= 1
    if size < 6:
        raise ValueError("无法在原字体高度范围内生成汉字")
    cells = []
    for code in additions:
        char = chr(code)
        left, top, right, bottom = han.getbbox(char, anchor="ls")
        w, h = max(1, right - left), max(1, bottom - top)
        y_offset = max(0, baseline + top)
        if y_offset + h > vertical_limit:
            raise ValueError("汉字超出行高，需要重新设置字体尺寸")
        mask = Image.new("L", (w, h))
        ImageDraw.Draw(mask).text((-left, -top), char, font=han, fill=255, anchor="ls")
        cells.append((code, mask, y_offset, round(han.getlength(char))))
    pitch_x = max(mask.width for _, mask, _, _ in cells) + 6
    pitch_y = max(mask.height for _, mask, _, _ in cells) + 6
    columns = max(1, (width - 6) // pitch_x)
    start_y = old_height + 6
    height = math.ceil((start_y + math.ceil(len(cells) / columns) * pitch_y + 3) / 4) * 4
    # Full-catalog Han coverage may need more columns. Widening the atlas keeps
    # all old glyph coordinates and pixels at their original positions.
    while height>4096 and width<4096:
        width=min(4096,width*2)
        columns=max(1,(width-6)//pitch_x)
        height=math.ceil((start_y+math.ceil(len(cells)/columns)*pitch_y+3)/4)*4
    if max(width, height) > 4096:
        raise ValueError("汉字字库超过 4096 像素纹理限制")
    extended = [Image.new("L", (width, height)) for _ in images]
    for new, old in zip(extended, images):
        new.paste(old, (0, 0))
    new_glyphs = []
    for index, (code, mask, y_offset, advance) in enumerate(cells):
        x = 3 + (index % columns) * pitch_x
        y = start_y + (index // columns) * pitch_y
        extended[0].paste(mask, (x, y))
        for shadow in extended[1:]:
            padded = Image.new("L", (mask.width + 6, mask.height + 6))
            padded.paste(mask, (3, 3))
            shadow.paste(padded.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(.65)), (x - 3, y - 3))
        right_bearing = max(-128, min(127, max(1, advance - mask.width + 1)))
        new_glyphs.append(Glyph(mask.width, mask.height, 0, right_bearing, y_offset, code, x, y))
    original_glyphs = list(font.glyphs)
    font.glyphs.extend(new_glyphs)
    if [g.codepoint for g in original_glyphs] == sorted(g.codepoint for g in original_glyphs):
        font.glyphs.sort(key=lambda g: g.codepoint)
    # Every original glyph's record and every original pixel is unchanged.
    by_code = {g.codepoint: g for g in font.glyphs}
    for glyph in original_glyphs:
        if by_code[glyph.codepoint] != glyph:
            raise ValueError("原字形指标改变")
    for new, old in zip(extended, images):
        if new.crop((0, 0, old_width, old_height)).tobytes() != old.tobytes():
            raise ValueError("原字形像素改变")
    textures = {struct.unpack_from("<I", raw)[0]: encode_alpha_texture(raw, image)
                for raw, image in zip(texture_raws, extended)}
    return font.serialize(), textures, {
        "new_glyphs": len(new_glyphs), "chinese_pixel_size": size, "baseline": baseline,
        "old_size": [old_width, old_height], "new_size": [width, height],
        "original_metrics_preserved": True, "original_pixels_preserved": True,
    }
