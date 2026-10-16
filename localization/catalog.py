"""Offline localization inventory. Reads original backup; never opens the game.

Retains fragment boundaries, dynamic references, argument strings and source
hashes. The older OCR index is deliberately not used to generate replacements.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lotro_zh.dat_reader import DatReader
from lotro_zh.text_resource import TextResource

BASELINE = ROOT / 'client_patch/backups/client_local_English.dat.original'
OUT = ROOT / 'localization'


def dump(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))


def build():
    OUT.mkdir(exist_ok=True)
    path = OUT / 'catalog.sqlite3'
    stage = OUT / 'catalog-building.sqlite3'
    if stage.exists():
        raise RuntimeError('Unfinished catalog exists; inspect it before rebuilding.')
    db = sqlite3.connect(stage)
    db.executescript('''
      CREATE TABLE resources(id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, title TEXT,
                             fragment_count INTEGER, trailing_bytes INTEGER);
      CREATE TABLE fragments(resource_id INTEGER, id INTEGER, pieces TEXT, refs TEXT, arguments TEXT,
                             PRIMARY KEY(resource_id,id));
      CREATE TABLE skipped(resource_id INTEGER PRIMARY KEY, reason TEXT);
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
    ''')
    parsed = fragments = skipped = 0
    with DatReader(BASELINE) as reader:
        for entry in reader.entries():
            if entry.resource_id >> 24 != 0x25:
                continue
            try:
                raw = reader.content(entry)
                text = TextResource.parse(raw)
                if text.serialize() != raw:
                    raise ValueError('Lossless roundtrip failed')
                title = next((''.join(f.pieces) for f in text.fragments if f.identifier == 228870261), '')
                title = title.encode('utf-8', errors='replace').decode('utf-8')
                db.execute('INSERT INTO resources VALUES(?,?,?,?,?)',
                           (entry.resource_id, hashlib.sha256(raw).hexdigest(), title,
                            len(text.fragments), len(text.trailing)))
                db.executemany('INSERT INTO fragments VALUES(?,?,?,?,?)',
                    [(entry.resource_id, f.identifier, dump(f.pieces),
                      dump([x.hex() for x in f.arg_refs]), dump(f.arg_strings)) for f in text.fragments])
                parsed += 1
                fragments += len(text.fragments)
            except (ValueError, UnicodeError) as error:
                skipped += 1
                db.execute('INSERT INTO skipped VALUES(?,?)',(entry.resource_id,str(error)))
            if (parsed + skipped) % 10000 == 0:
                db.commit()
                print(f'Inventory: {parsed} resources, {fragments} fragments, {skipped} skipped',flush=True)
    summary = {'resources':parsed,'fragments':fragments,'skipped':skipped,
               'source':str(BASELINE),'deployment_enabled':False,
               'note':'Counts are text resources/fragments, not quests or translated strings.'}
    db.execute('INSERT INTO metadata VALUES(?,?)',('summary',dump(summary)))
    db.commit()
    db.close()
    stage.replace(path)
    (OUT/'inventory-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    build()
