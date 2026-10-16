"""Strict, lossless container handling for the client's localized JPEG maps."""
from io import BytesIO
import struct
from PIL import Image


def jpeg_texture(raw):
    if len(raw)<28:raise ValueError('Truncated JPEG texture')
    rid,flags,width,height,fmt,size=struct.unpack_from('<6I',raw)
    if rid>>24!=0x41 or fmt!=500 or size!=len(raw)-24:
        raise ValueError('Invalid JPEG texture header')
    jpeg=raw[24:]
    if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
        raise ValueError('Invalid JPEG markers')
    with Image.open(BytesIO(jpeg)) as image:
        if image.format!='JPEG':raise ValueError('Texture is not JPEG')
        image.load();dimensions=image.size
    if width not in (0,dimensions[0]) or height not in (0,dimensions[1]):
        raise ValueError('JPEG texture dimensions disagree')
    return rid,dimensions,jpeg
