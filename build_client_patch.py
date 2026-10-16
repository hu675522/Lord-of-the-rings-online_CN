"""Build a task-scoped, hash-verified client patch on disposable copies."""
import argparse
import copy
from contextlib import ExitStack
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from lotro_zh.dat_reader import DatReader
from lotro_zh.font_resource import BitmapFont, alpha_texture, extend_font
from lotro_zh.text_resource import TextResource

ROOT = Path(__file__).resolve().parent
PATCH = ROOT / "client_patch"
PYTHON = json.loads((ROOT / "runtime.json").read_text(encoding="utf-8"))["python"]


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def byte_hash(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def collect(reader):
    return {entry.resource_id: entry for entry in reader.entries()}


def source_archive(install, name, from_backups=False):
    return PATCH / "backups" / (name + ".original") if from_backups else install / name


def build_payloads(install, from_backups=False):
    package = PATCH / "package"
    records_dir = package / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    plans = [json.loads((PATCH / "translations" / name).read_text(encoding="utf-8"))
             for name in ("finding-amdir.json", "madness-at-damudur.json")]
    changed = []
    all_chars = set()
    language_records, fonts_report = [], []
    surface_records = {"client_surface.dat": [], "client_surface_aux_1.datx": []}

    def record(raw, old, destination):
        rid = int.from_bytes(raw[:4], "little")
        path = records_dir / f"{rid:08X}.bin"
        path.write_bytes(raw)
        destination.append({"id": rid, "file": "records/" + path.name, "sha256": byte_hash(raw),
                            "original_sha256": byte_hash(old), "bytes": len(raw)})

    with ExitStack() as stack:
        language = stack.enter_context(DatReader(source_archive(install, "client_local_English.dat", from_backups)))
        le = collect(language)
        wanted_textures = {tid for entry in le.values() if entry.resource_id >> 24 == 0x42
                           for tid in BitmapFont.parse(language.content(entry)).textures if tid}
        texture_sources = {}
        for name in surface_records:
            reader = stack.enter_context(DatReader(source_archive(install, name, from_backups)))
            for entry in reader.entries():
                if entry.resource_id in wanted_textures:
                    texture_sources[entry.resource_id] = (reader, entry, name)
        if set(texture_sources) != wanted_textures:
            raise ValueError("仍有字体纹理未定位，停止构建")

        def get_texture(tid):
            reader, entry, _ = texture_sources[tid]
            return reader.content(entry)
        for plan in plans:
            did = int(plan["resource_id"], 16)
            snapshot = ROOT / plan.get("source_snapshot", "artifacts/client-patch-probe/2500020B.original.bin")
            raw = language.content(le[did])
            if raw != snapshot.read_bytes():
                raise ValueError("任务原文已变化，需重新审核译文：" + plan["task"])
            text = TextResource.parse(raw)
            if text.serialize() != raw:
                raise ValueError("任务资源原始往返不一致")
            if {str(f.identifier) for f in text.fragments} != set(plan["fragments"]):
                raise ValueError("译文没有完整覆盖该任务的所有片段")
            original = copy.deepcopy(text)
            for fragment in text.fragments:
                pieces = plan["fragments"][str(fragment.identifier)]
                if len(pieces) != len(fragment.pieces):
                    raise ValueError("动态文字分段数变化")
                changed.append({"resource_id": plan["resource_id"], "task": plan["task"],
                                "fragment_id": str(fragment.identifier), "source_pieces": fragment.pieces,
                                "chinese_pieces": pieces, "dynamic_arguments": [x.hex() for x in fragment.arg_refs]})
                fragment.pieces = pieces
                all_chars.update(c for piece in pieces for c in piece if ord(c) > 127)
            patched = text.serialize()
            reparsed = TextResource.parse(patched)
            for before, after in zip(original.fragments, reparsed.fragments):
                if (before.identifier, len(before.pieces), before.arg_refs, before.arg_strings) != (after.identifier, len(after.pieces), after.arg_refs, after.arg_strings):
                    raise ValueError("任务动态参数结构变化")
            record(patched, raw, language_records)
        pending_textures = {}
        for entry in le.values():
            if entry.resource_id >> 24 != 0x42:
                continue
            raw_font = language.content(entry)
            font = BitmapFont.parse(raw_font)
            textures = [get_texture(tid) for tid in font.textures if tid]
            new_font, new_textures, stats = extend_font(raw_font, textures, all_chars, Path(r"C:\Windows\Fonts\msyh.ttc"))
            if new_font != raw_font:
                record(new_font, raw_font, language_records)
                for tid, new_raw in new_textures.items():
                    if tid in pending_textures and pending_textures[tid] != new_raw:
                        raise ValueError("共享纹理修改不一致")
                    pending_textures[tid] = new_raw
            stats.update(id=f"0x{font.identifier:08X}", font_height=font.height, line_height=font.line_height)
            fonts_report.append(stats)
        for tid, new_raw in pending_textures.items():
            record(new_raw, get_texture(tid), surface_records[texture_sources[tid][2]])
        preview_font = BitmapFont.parse(language.content(le[0x42000019]))
        tid = preview_font.textures[0]
        alpha_texture(pending_textures[tid]).save(package / "font-atlas-preview.png")
    report = {"task": " + ".join(p["task"] for p in plans), "text_resources": len(plans), "translated_fragments": len(changed),
              "new_characters": "".join(sorted(all_chars)), "fonts": fonts_report,
              "font_count": len(fonts_report), "texture_count": sum(len(x) for x in surface_records.values()),
              "changes": changed, "game_rendering_verified": False}
    write_json(package / "translation-review.json", report)
    # DatExport opens the master surface DAT plus all of its *_aux_N.datx
    # extents. Expanded resources can move between extents. Never patch an
    # extent in isolation or assume a resource stays in its original file.
    return {"client_local_English.dat": language_records,
            "client_surface.dat": [record for group in surface_records.values() for record in group]}, report


def make_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    print("Copying " + str(source) + " -> " + str(target), flush=True)
    shutil.copyfile(source, target)


def validate_records(archives, records, expected_untouched=None):
    with ExitStack() as stack:
        locations = {}
        for archive in archives:
            reader = stack.enter_context(DatReader(archive))
            for entry in reader.entries():
                locations[entry.resource_id] = (reader, entry)
        for record in records:
            if record["id"] not in locations:
                raise ValueError("补丁资源缺失：" + hex(record["id"]))
            reader, entry = locations[record["id"]]
            payload = reader.content(entry)
            if byte_hash(payload) != record["sha256"]:
                raise ValueError("独立读取器校验补丁资源失败：" + hex(record["id"]))
            if record["id"] >> 24 == 0x42:
                parsed = BitmapFont.parse(payload)
                if parsed.serialize() != payload:
                    raise ValueError("字体重新解析不一致")
            elif record["id"] >> 24 == 0x41:
                alpha_texture(payload)
            elif record["id"] >> 24 == 0x25:
                if TextResource.parse(payload).serialize() != payload:
                    raise ValueError("文本重新解析不一致")
        if expected_untouched is None:
            excluded = {record["id"] for record in records}
            choices = sorted(did for did, (_, entry) in locations.items()
                             if did >> 24 not in (0x78, 0xff) and did not in excluded
                             and 4 <= entry.size <= 4 * 1024 * 1024)
            expected_untouched = {}
            for i in range(min(64, len(choices))):
                did = choices[i * len(choices) // min(64, len(choices))]
                reader, entry = locations[did]
                expected_untouched[did] = byte_hash(reader.content(entry))
        else:
            for did, expected in expected_untouched.items():
                reader, entry = locations[did]
                if byte_hash(reader.content(entry)) != expected:
                    raise ValueError("抽查的未修改资源发生变化：" + hex(did))
        return {did for did in locations if did < 0xff000000}, expected_untouched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", default=r"D:\Program Files\StandingStoneGames\The Lord of the Rings Online")
    parser.add_argument("--payloads-only", action="store_true")
    parser.add_argument("--from-backups", action="store_true", help="Build from verified original backups while the game is running")
    args = parser.parse_args()
    install = Path(args.install_dir).resolve()
    previous_plan = None
    previous_path = PATCH / "revisions/amdir-v1/install-plan.json"
    if args.from_backups:
        previous_plan = json.loads(previous_path.read_text(encoding="utf-8"))
        for archive in previous_plan["archives"]:
            if file_hash(PATCH / "backups" / (archive["name"] + ".original")) != archive["original_sha256"]:
                raise ValueError("原始备份与旧版记录不同")
    active_plan = PATCH / "package/install-plan.json"
    if active_plan.exists():
        pending = json.loads(active_plan.read_text(encoding="utf-8"))
        pending["all_workspace_checks_passed"] = False
        write_json(active_plan, pending)
    records, report = build_payloads(install, args.from_backups)
    print(f"Prepared {report['translated_fragments']} text fragments, {report['font_count']} fonts, {report['texture_count']} textures", flush=True)
    if args.payloads_only:
        return
    backups = PATCH / "backups"
    work = PATCH / "work"
    package = PATCH / "package"
    installed = {"schema": 1, "install_directory": str(install), "task": report["task"], "archives": [],
                 "game_rendering_verified": False, "all_workspace_checks_passed": False}
    names = ["client_local_English.dat", "client_surface.dat", "client_surface_aux_1.datx", "client_surface_aux_2.datx"]
    originals = {}
    for name in names:
        source = source_archive(install, name, args.from_backups)
        before_stat = source.stat()
        source_sha = file_hash(source)
        backup = backups / (name + ".original")
        if backup.exists():
            if file_hash(backup) != source_sha:
                raise ValueError("已有备份与当前游戏文件不同，保留备份并停止：" + name)
        else:
            make_copy(source, backup)
            if file_hash(backup) != source_sha:
                raise ValueError("备份校验失败")
        if (source.stat().st_size, source.stat().st_mtime_ns) != (before_stat.st_size, before_stat.st_mtime_ns):
            raise ValueError("备份期间源文件变化")
        working = work / name
        make_copy(backup, working)
        originals[name] = {"original_sha256": source_sha, "original_size": before_stat.st_size,
                           "backup": str(backup), "candidate": str(working)}
    groups = {"client_local_English.dat": ["client_local_English.dat"],
              "client_surface.dat": names[1:]}
    original_ids, untouched = {}, {}
    for master, children in groups.items():
        original_ids[master], samples = validate_records([work / name for name in children], [])
        excluded = {record["id"] for record in records[master]}
        untouched[master] = {did: sha for did, sha in samples.items() if did not in excluded}
        write_json(package / (master + ".manifest.json"),
                   {"archive_sha256": originals[master]["original_sha256"], "records": records[master]})

    def apply_and_check():
        for master, children in groups.items():
            print("Applying complete archive group: " + master, flush=True)
            subprocess.run([str(PATCH / "tools/DatPatchWorker.exe"), "apply", str(work / master),
                            str(package / (master + ".manifest.json"))], cwd=PATCH / "tools", check=True, timeout=180)
            current_ids, _ = validate_records([work / name for name in children], records[master], untouched[master])
            if current_ids != original_ids[master]:
                raise ValueError("修改前后整组公开资源 ID 集合不同")
            print("All replacement payloads and full public resource-ID set verified: " + master, flush=True)

    apply_and_check()
    print("Testing complete archive-group restoration", flush=True)
    for name in names:
        make_copy(Path(originals[name]["backup"]), work / name)
        if file_hash(work / name) != originals[name]["original_sha256"]:
            raise ValueError("整组副本还原校验失败：" + name)
    print("All original hashes restored; rebuilding final candidates", flush=True)
    apply_and_check()
    for name in names:
        working = work / name
        installed["archives"].append({"name": name, "original_sha256": originals[name]["original_sha256"],
                                      "patched_sha256": file_hash(working), "original_size": originals[name]["original_size"],
                                      "candidate_size": working.stat().st_size,
                                      "backup": originals[name]["backup"], "candidate": str(working),
                                      "resource_count": len(records.get(name, [])), "restore_on_copy_verified": True})
        if previous_plan:
            prior = next(a for a in previous_plan["archives"] if a["name"] == name)
            previous_candidate = work / "previous" / name
            if file_hash(previous_candidate) != prior["patched_sha256"]:
                raise ValueError("上版候选副本校验失败")
            installed["archives"][-1].update(previous_sha256=prior["patched_sha256"],
                                              previous_candidate=str(previous_candidate))
    installed["all_workspace_checks_passed"] = True
    installed["untouched_resource_samples_verified"] = {name: len(samples) for name, samples in untouched.items()}
    write_json(package / "install-plan.json", installed)
    print("READY: " + str(package / "install-plan.json"), flush=True)


if __name__ == "__main__":
    main()
