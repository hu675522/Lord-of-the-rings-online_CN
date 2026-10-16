"""Read-only Turbine DAT inspection. Never opens a game archive for writing.

Container layout reference:
https://github.com/Mirarkitty/lotro_mesh_viewer/blob/master/datfile.py
Text extraction is deliberately a candidate extractor, not a complete parser of
LOTRO's string-table grammar. Resource IDs and original segments are retained.
"""
from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    resource_id: int
    offset: int
    size: int
    block_size: int
    flags: int


class DatError(ValueError):
    pass


class DatReader:
    MAX_RESOURCE = 16 * 1024 * 1024

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.stream = self.path.open("rb")
        try:
            self.length = self.path.stat().st_size
            header = self._read(0, 2048)
            if self._u32(header, 0x101) != 0x4C50 or self._u32(header, 0x140) != 0x5442:
                raise DatError("不是支持的 Turbine DAT 文件")
            self.root = self._u32(header, 0x160)
        except Exception:
            self.close()
            raise

    @staticmethod
    def _u32(data, offset=0):
        return struct.unpack_from("<I", data, offset)[0]

    def _read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.length:
            raise DatError("资源范围超出文件边界")
        self.stream.seek(offset)
        data = self.stream.read(size)
        if len(data) != size:
            raise DatError("资源读取不完整")
        return data

    def entries(self):
        stack, visited = [self.root], set()
        while stack:
            offset = stack.pop()
            if offset in visited or len(visited) > 200_000:
                raise DatError("资源目录存在循环或节点过多")
            visited.add(offset)
            node = self._read(offset, 508)
            count = self._u32(node, 504)
            if node[:8] != bytes(8) or count > 61:
                raise DatError("不支持的资源目录结构")
            for index in range(min(62, count + 1)):
                size, child = struct.unpack_from("<II", node, 8 + index * 8)
                if not size:
                    break
                stack.append(child)
            raw = self._read(offset + 508, count * 32)
            for index in range(count):
                flags, did, pos, size, _, _, block_size, _ = struct.unpack_from("<8I", raw, index * 32)
                if size:
                    yield Entry(did, pos, size, block_size, flags & 0xFFFF)

    def content(self, entry: Entry, *, validate_identifier=True):
        """Read a payload; opaque UI records need not embed their directory ID.

        Text/fonts/textures keep strict ID validation by default. Disabling it
        is only for byte comparison of unchanged, opaque source records.
        """
        if entry.size > self.MAX_RESOURCE or entry.block_size > self.MAX_RESOURCE:
            raise DatError("单个资源过大，原型跳过")
        extra, legacy = struct.unpack("<II", self._read(entry.offset, 8))
        if legacy or extra > 65536:
            raise DatError("不支持的资源分块格式")
        first = min(entry.size, entry.block_size - 8 - extra * 8)
        if first < 0:
            raise DatError("无效的资源分块长度")
        raw = bytearray(self._read(entry.offset + 8, first))
        table = self._read(entry.offset + 8 + first, extra * 8)
        for index in range(extra):
            size, offset = struct.unpack_from("<II", table, index * 8)
            needed = min(size, entry.size - len(raw))
            if needed > 0:
                raw.extend(self._read(offset, needed))
        if len(raw) != entry.size:
            raise DatError("资源分块缺失")
        if entry.flags & 1:
            if len(raw) < 4 or self._u32(raw) > self.MAX_RESOURCE:
                raise DatError("解压后的资源过大")
            decoder = zlib.decompressobj()
            result = decoder.decompress(raw[4:], self.MAX_RESOURCE + 1)
            if len(result) > self.MAX_RESOURCE or not decoder.eof:
                raise DatError("压缩资源损坏或超限")
            raw = result
        if validate_identifier and (len(raw) < 4 or self._u32(raw) != entry.resource_id):
            raise DatError("资源 ID 不匹配")
        return bytes(raw)

    def close(self):
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# UTF-16 text may begin at either byte alignment because lengths are variable.
# Restrict candidates to Latin text/markup and common typographic punctuation;
# preserve whitespace and placeholders rather than inventing missing values.
_RUN = re.compile(r"[\x09\x0a\x0d\x20-\x7e\u00a0-\u024f\u2010-\u2026]{4,}")


def text_candidates(raw: bytes):
    seen = set()
    for alignment in (0, 1):
        text = raw[4 + alignment:].decode("utf-16-le", errors="replace")
        for match in _RUN.finditer(text):
            value = match.group().strip()
            if len(value) < 4 or len(value) > 24000:
                continue
            if len(re.findall(r"[A-Za-z]", value)) < 4:
                continue
            if value not in seen:
                seen.add(value)
                yield value
