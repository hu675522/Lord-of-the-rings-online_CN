from __future__ import annotations

import difflib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from .dat_reader import DatReader, DatError, text_candidates


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    text = re.sub(r"<[^>]*>", " ", text)
    return " ".join(re.findall(r"[\w]+", text, re.UNICODE))


class Store:
    def __init__(self, directory: Path, seed_path: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "catalog.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS texts(
            id INTEGER PRIMARY KEY, resource_id INTEGER NOT NULL,
            segment INTEGER NOT NULL, text TEXT NOT NULL, norm TEXT UNIQUE NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS texts_fts USING fts5(text, content='texts', content_rowid='id');
        CREATE TABLE IF NOT EXISTS translations(
            norm TEXT PRIMARY KEY, source TEXT NOT NULL, zh TEXT NOT NULL,
            origin TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        for item in json.loads(seed_path.read_text(encoding="utf-8")):
            self.db.execute("INSERT OR IGNORE INTO translations(norm,source,zh,origin) VALUES(?,?,?,'sample')",
                            (normalize(item["source"]), item["source"], item["zh"]))
        self.db.commit()

    def close(self):
        self.db.close()

    def status(self):
        meta = {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT key,value FROM metadata")}
        return {"text_count": self.db.execute("SELECT COUNT(*) FROM texts").fetchone()[0],
                "translation_count": self.db.execute("SELECT COUNT(*) FROM translations").fetchone()[0],
                "metadata": meta}

    def build(self, install_dir, progress=lambda _: None):
        archive = Path(install_dir) / "client_local_English.dat"
        stat = archive.stat()
        signature = {"path": str(archive.resolve()), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                     "extractor": 3}
        previous = self.db.execute("SELECT value FROM metadata WHERE key='archive'").fetchone()
        if previous and json.loads(previous[0]) == signature:
            return dict(self.status(), reused=True)
        # Build in a separate DB. A cancelled/failed extraction keeps the last
        # working index; user translations are never cleared during rebuilding.
        staging = self.directory / "index-building.sqlite3"
        temp = sqlite3.connect(staging)
        resources = skipped = 0
        try:
            temp.executescript("DROP TABLE IF EXISTS candidates; CREATE TABLE candidates(resource_id INTEGER, segment INTEGER, text TEXT, norm TEXT UNIQUE);")
            with DatReader(archive) as reader:
                batch = []
                for entry in reader.entries():
                    if entry.resource_id >> 24 != 0x25:
                        continue
                    resources += 1
                    try:
                        for segment, text in enumerate(text_candidates(reader.content(entry))):
                            norm = normalize(text)
                            if len(norm) >= 4:
                                batch.append((entry.resource_id, segment, text, norm))
                    except (DatError, UnicodeError, ValueError):
                        skipped += 1
                    if resources % 2000 == 0:
                        temp.executemany("INSERT OR IGNORE INTO candidates VALUES(?,?,?,?)", batch)
                        temp.commit()
                        batch.clear()
                        progress({"resources": resources, "message": "正在读取本地英文文本候选"})
                temp.executemany("INSERT OR IGNORE INTO candidates VALUES(?,?,?,?)", batch)
                temp.commit()
            after = archive.stat()
            if after.st_size != stat.st_size or after.st_mtime_ns != stat.st_mtime_ns:
                raise ValueError("游戏文件在提取期间发生变化，请等待游戏更新完成后重试。")
            temp.close()
            temp = None
            self.db.execute("ATTACH DATABASE ? AS staging", (str(staging),))
            try:
                with self.db:
                    self.db.execute("DELETE FROM texts")
                    self.db.execute("INSERT INTO texts(resource_id,segment,text,norm) SELECT resource_id,segment,text,norm FROM staging.candidates")
                    self.db.execute("INSERT INTO texts_fts(texts_fts) VALUES('rebuild')")
                    self.db.execute("INSERT OR REPLACE INTO metadata VALUES('archive',?)", (json.dumps(signature),))
                    self.db.execute("INSERT OR REPLACE INTO metadata VALUES('extraction',?)",
                                    (json.dumps({"resources": resources, "skipped": skipped, "method": "UTF-16 candidate extraction"}),))
            finally:
                self.db.execute("DETACH DATABASE staging")
        finally:
            if temp is not None:
                temp.close()
            staging.unlink(missing_ok=True)
        return dict(self.status(), reused=False)

    def lookup(self, text):
        row = self.db.execute("SELECT source,zh,origin FROM translations WHERE norm=?", (normalize(text),)).fetchone()
        return dict(row) if row else {"source": text, "zh": "", "origin": "missing"}

    def save(self, source, zh):
        source, zh = source.strip(), zh.strip()
        if not normalize(source) or not zh:
            raise ValueError("英文原文和中文译文均不能为空。")
        if len(source) > 24000 or len(zh) > 40000:
            raise ValueError("文本超过原型支持的长度。")
        with self.db:
            self.db.execute("INSERT INTO translations(norm,source,zh,origin) VALUES(?,?,?,'user') ON CONFLICT(norm) DO UPDATE SET source=excluded.source,zh=excluded.zh,origin='user',updated=CURRENT_TIMESTAMP",
                            (normalize(source), source, zh))
        return self.lookup(source)

    def search(self, query, limit=18):
        query = query.strip()[:24000]
        norm = normalize(query)
        if not norm:
            return {"items": [], "translation": self.lookup(query)}
        found = {}
        for row in self.db.execute("SELECT resource_id,segment,text,norm FROM texts WHERE norm=? LIMIT 1", (norm,)):
            found[row["norm"]] = dict(row, score=1.0, match="exact")
        # OCR returns separate lines. A title can be identified even when a
        # selection also contains objectives or other nearby text. It remains
        # a candidate; the full OCR result is not silently replaced.
        for line in query.splitlines()[:40]:
            line_norm = normalize(line)
            if len(line_norm) < 6 or line_norm == norm:
                continue
            for row in self.db.execute("SELECT resource_id,segment,text,norm FROM texts WHERE norm=? LIMIT 1", (line_norm,)):
                found[row["norm"]] = dict(row, score=.99, match="line")
        tokens = [w for w in norm.split() if len(w) > 2][:24]
        if tokens:
            fts_query = " OR ".join('"' + word.replace('"', '""') + '"' for word in dict.fromkeys(tokens))
            for row in self.db.execute("SELECT t.resource_id,t.segment,t.text,t.norm FROM texts_fts f JOIN texts t ON t.id=f.rowid WHERE texts_fts MATCH ? ORDER BY bm25(texts_fts) LIMIT 100", (fts_query,)):
                value = dict(row)
                score = difflib.SequenceMatcher(None, norm, row["norm"], autojunk=False).ratio()
                if norm in row["norm"]:
                    score = max(score, .70 + .25 * len(norm) / max(1, len(row["norm"])))
                value.update(score=round(score, 3), match="candidate")
                if row["norm"] not in found:
                    found[row["norm"]] = value
        # Translated samples remain usable before the full game index is built.
        for row in self.db.execute("SELECT source,zh,origin,norm FROM translations"):
            if norm in row["norm"] or row["norm"] in norm:
                if row["norm"] not in found:
                    partial_score = .60 + .15 * min(len(row["norm"]) / max(1, len(norm)), 1)
                    found[row["norm"]] = {"resource_id": 0, "segment": 0, "text": row["source"],
                                          "norm": row["norm"], "score": 1.0 if norm == row["norm"] else partial_score,
                                          "match": "exact" if norm == row["norm"] else "candidate"}
        items = sorted(found.values(), key=lambda x: x["score"], reverse=True)[:limit]
        for item in items:
            item["translation"] = self.lookup(item["text"])
            item["resource_label"] = "0x%08X" % item["resource_id"] if item["resource_id"] else "离线示例 / 自存译文"
            item.pop("norm", None)
        # Never silently replace OCR with a fuzzy candidate or its translation.
        return {"items": items, "translation": self.lookup(query)}

    def samples(self):
        return [dict(row) for row in self.db.execute("SELECT source,zh,origin FROM translations WHERE origin='sample' ORDER BY rowid LIMIT 40")]
