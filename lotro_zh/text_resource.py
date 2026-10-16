"""Lossless text-subresource codec for the client-patch feasibility probe.

The container is kept separate from the DAT archive. This module does not write
to game archives. Layout cross-checked against Elanor TextSubfile.cs and the
LotroKoniecDev SubFile/Fragment implementation. No third-party implementation is
bundled or executed.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass


class TextFormatError(ValueError):
    pass


class Cursor:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, length):
        if length < 0 or self.position + length > len(self.data):
            raise TextFormatError("文本资源被截断")
        result = self.data[self.position:self.position + length]
        self.position += length
        return result

    def number(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def variable(self):
        first = self.number("<B")
        return ((first & 0x7f) << 8) | self.number("<B") if first & 0x80 else first

    def count(self, item_minimum):
        count = self.number("<I")
        if count > (len(self.data) - self.position) // item_minimum:
            raise TextFormatError("文本资源计数超过剩余数据")
        return count

    def text(self):
        return self.take(self.variable() * 2).decode("utf-16-le", errors="surrogatepass")


def variable(value):
    if not 0 <= value <= 32767:
        raise TextFormatError("长度超出 15 位编码范围")
    return bytes((value,)) if value < 128 else bytes((0x80 | (value >> 8), value & 255))


def encode_text(text):
    raw = text.encode("utf-16-le", errors="surrogatepass")
    return variable(len(raw) // 2) + raw


@dataclass
class Fragment:
    identifier: int
    pieces: list[str]
    arg_refs: list[bytes]
    arg_strings: list[list[str]]

    def serialize(self):
        result = bytearray(struct.pack("<QI", self.identifier, len(self.pieces)))
        for piece in self.pieces:
            result.extend(encode_text(piece))
        result.extend(struct.pack("<I", len(self.arg_refs)))
        for arg in self.arg_refs:
            if len(arg) != 4:
                raise TextFormatError("动态参数引用必须为 4 字节")
            result.extend(arg)
        if len(self.arg_strings) > 255:
            raise TextFormatError("参数字符串组数超限")
        result.append(len(self.arg_strings))
        for group in self.arg_strings:
            result.extend(struct.pack("<I", len(group)))
            for text in group:
                result.extend(encode_text(text))
        return bytes(result)


@dataclass
class TextResource:
    identifier: int
    unknown: bytes
    fragments: list[Fragment]
    trailing: bytes = b""

    @classmethod
    def parse(cls, raw):
        cursor = Cursor(raw)
        identifier = cursor.number("<I")
        if identifier >> 24 != 0x25:
            raise TextFormatError("资源不是 0x25 文本类型")
        unknown = cursor.take(5)
        count = cursor.variable()
        if count > (len(raw) - cursor.position) // 17:
            raise TextFormatError("文本片段计数超限")
        fragments = []
        for _ in range(count):
            fragment_id = cursor.number("<Q")
            pieces = [cursor.text() for _ in range(cursor.count(1))]
            refs = [cursor.take(4) for _ in range(cursor.count(4))]
            group_count = cursor.number("<B")
            groups = [[cursor.text() for _ in range(cursor.count(1))] for _ in range(group_count)]
            fragments.append(Fragment(fragment_id, pieces, refs, groups))
        return cls(identifier, unknown, fragments, raw[cursor.position:])

    def serialize(self):
        if len(self.unknown) != 5:
            raise TextFormatError("资源未知头部长度变化")
        return (struct.pack("<I", self.identifier) + self.unknown + variable(len(self.fragments))
                + b"".join(fragment.serialize() for fragment in self.fragments) + self.trailing)
