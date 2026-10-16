"""Prepare inspectable text candidates and font coverage report, not a patcher.

Only the workspace output directory is written. No DAT mutation API exists in
this script. Its .bin outputs cannot be copied directly into the game folder.
"""
import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path

from lotro_zh.dat_reader import DatReader
from lotro_zh.text_resource import TextResource

TARGET_IDS = {0x2500020B, 0x2500020F, 0x25003524}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", default=r"D:\Program Files\StandingStoneGames\The Lord of the Rings Online")
    parser.add_argument("--output", default="artifacts/client-patch-probe")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    installation = Path(args.install_dir).resolve()
    # All generated files must stay in this project, outside the live install.
    output.relative_to(Path(__file__).resolve().parent)
    if output == installation or installation in output.parents:
        raise ValueError("输出目录不能位于游戏安装目录")
    output.mkdir(parents=True, exist_ok=True)
    seeds = json.loads((Path(__file__).resolve().parent / "samples.json").read_text(encoding="utf-8"))
    translations = {row["source"]: row["zh"] for row in seeds}
    archive = installation / "client_local_English.dat"
    before = archive.stat()
    fonts, resources, changes, texture_ids = [], [], [], set()
    with DatReader(archive) as reader:
        entries = list(reader.entries())
        by_id = {e.resource_id: e for e in entries}
        for entry in entries:
            if entry.resource_id >> 24 != 0x42:
                continue
            raw = reader.content(entry)
            did, size, baseline, count = struct.unpack_from("<4I", raw)
            if len(raw) != 36 + count * 11:
                raise ValueError("字体记录布局与参考格式不符")
            codes = {struct.unpack_from("<H", raw, 21 + i * 11)[0] for i in range(count)}
            textures = struct.unpack_from("<2I", raw, len(raw) - 8)
            texture_ids.update(textures)
            fonts.append({"id": f"0x{did:08X}", "size": size, "glyph_count": count,
                          "cjk_unified_count": sum(0x3400 <= c <= 0x9fff for c in codes),
                          "codepoints": sorted(codes), "textures": [f"0x{x:08X}" for x in textures]})
        for did in sorted(TARGET_IDS):
            raw = reader.content(by_id[did])
            original = TextResource.parse(raw)
            if original.serialize() != raw:
                raise ValueError(f"0x{did:08X} 无修改往返不一致，停止生成")
            modified = copy.deepcopy(original)
            local_changes = []
            for fragment in modified.fragments:
                # The first proof only translates complete, single-piece text.
                # Multi-piece dynamic templates are preserved without edits.
                if len(fragment.pieces) != 1 or fragment.arg_refs:
                    continue
                source = fragment.pieces[0]
                if source not in translations:
                    continue
                chinese = translations[source]
                if "\\n" in source:
                    chinese = chinese.replace("\r\n", "\n").replace("\n", "\\n")
                fragment.pieces[0] = chinese
                local_changes.append({"fragment_id": str(fragment.identifier), "source": source, "zh": chinese})
            patched = modified.serialize()
            reparsed = TextResource.parse(patched)
            if reparsed.serialize() != patched:
                raise ValueError("中文候选资源重新读取失败")
            for old, new in zip(original.fragments, reparsed.fragments):
                if (old.identifier != new.identifier or len(old.pieces) != len(new.pieces)
                        or old.arg_refs != new.arg_refs or old.arg_strings != new.arg_strings):
                    raise ValueError("动态参数或片段结构发生变化")
            # Raw subresources are proof artifacts, not DAT replacement files.
            (output / f"{did:08X}.original.bin").write_bytes(raw)
            (output / f"{did:08X}.chinese-candidate.bin").write_bytes(patched)
            resources.append({"id": f"0x{did:08X}", "fragments": len(original.fragments),
                              "unchanged_roundtrip_identical": True, "original_sha256": digest(raw),
                              "candidate_sha256": digest(patched), "changes": local_changes,
                              "arguments_preserved": True, "original_bytes": len(raw), "candidate_bytes": len(patched)})
            changes.extend(local_changes)
        textures = []
        for did in sorted(texture_ids):
            entry = by_id.get(did)
            if entry is None:
                textures.append({"id": f"0x{did:08X}", "present": False})
                continue
            raw = reader.content(entry)
            textures.append({"id": f"0x{did:08X}", "present": True, "bytes": len(raw),
                             "first_32_bytes_hex": raw[:32].hex()})
    after = archive.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("扫描期间语言包发生变化，结果不应作为补丁依据")
    used = {ord(c) for row in changes for c in row["zh"] if ord(c) > 127}
    available = set().union(*(set(f["codepoints"]) for f in fonts))
    missing = sorted(used - available)
    report = {"mode": "read-only feasibility probe; not an installable patch",
              "archive": str(archive), "archive_size": before.st_size, "archive_unchanged_by_stat": True,
              "font_count": len(fonts), "cjk_unified_glyphs_in_scanned_fonts": sum(f["cjk_unified_count"] for f in fonts),
              "missing_characters_for_candidate": "".join(chr(x) for x in missing),
              "missing_codepoints_for_candidate": [f"U+{x:04X}" for x in missing],
              "fonts": fonts, "font_texture_records": textures, "resources": resources,
              "translated_fragments": len(changes),
              "blocked_before_client_test": ["Generate compatible Chinese glyph atlases and font tables",
                                              "Validate DAT write-back and restore on a working copy",
                                              "In-game font/layout test"]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("font_count", "cjk_unified_glyphs_in_scanned_fonts",
                                                  "translated_fragments", "missing_characters_for_candidate")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
