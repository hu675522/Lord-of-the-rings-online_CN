"""Reassemble full-catalog drafts into a local, non-deployable BLOB archive."""
import collections
import copy
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from localization.full_translate import BASE,OUT,dumps,connect
from localization.build_batch import SOURCE,validate_pieces,controls,validate_fragment
from lotro_zh.dat_reader import DatReader
from lotro_zh.text_resource import TextResource


def reconstruct(piece,templates,segments):
    template=templates[dumps(piece)]
    source=''.join(atom['keep'] if 'keep' in atom else segments[atom['segment']][0] for atom in template)
    if source!=piece:raise ValueError('Source template is not lossless')
    result=[];flags=set()
    for atom in template:
        if 'keep' in atom:result.append(atom['keep'])
        else:
            _,target,status,qa=segments[atom['segment']]
            if status not in {'glossary','machine_draft','reviewed_correction','technical_preserved'} or target is None:
                raise ValueError('Unfinished model segment')
            result.append(target)
            if qa:flags.update(qa.split(','))
    return ''.join(result),flags


def compare_structure(original,translated):
    if (original.identifier,original.unknown,original.trailing,len(original.fragments))!=(
        translated.identifier,translated.unknown,translated.trailing,len(translated.fragments)):
        raise ValueError('Text resource framing changed')
    for left,right in zip(original.fragments,translated.fragments):
        if (left.identifier,left.arg_refs,left.arg_strings)!=(right.identifier,right.arg_refs,right.arg_strings):
            raise ValueError('Dynamic argument metadata changed')
        validate_fragment(original.identifier,left.pieces,right.pieces)


def build():
    jobs=connect()
    unfinished=jobs.execute("SELECT count(*) FROM segments WHERE status NOT IN ('glossary','machine_draft','reviewed_correction','technical_preserved')").fetchone()[0]
    if unfinished:raise ValueError(f'{unfinished} translation units unfinished; export blocked')
    segments={sid:(s,t,status,qa) for sid,s,t,status,qa in jobs.execute('SELECT id,source,translation,status,qa FROM segments')}
    templates={s:json.loads(t) for s,t in jobs.execute('SELECT source_json,template FROM pieces')}
    overrides={(r,f):json.loads(p) for r,f,p in jobs.execute('SELECT resource_id,fragment_id,pieces FROM overrides')}
    preserved={(r,f):reason for r,f,reason in jobs.execute('SELECT * FROM preserved')}
    jobs.close()
    catalog=sqlite3.connect(BASE/'catalog.sqlite3')
    hashes=dict(catalog.execute('SELECT id,sha256 FROM resources'))
    catalog.close()
    dest=OUT/'text-resources.building.sqlite3'
    if dest.exists():dest.unlink()
    archive=sqlite3.connect(dest)
    archive.executescript('''
      CREATE TABLE resources(id INTEGER PRIMARY KEY,source_sha256 TEXT,payload_sha256 TEXT,payload BLOB,
                             changed_fragments INTEGER);
      CREATE TABLE review(resource_id INTEGER,fragment_id INTEGER,source_pieces TEXT,chinese_pieces TEXT,
                          status TEXT,qa TEXT,PRIMARY KEY(resource_id,fragment_id));
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
    ''')
    counts=collections.Counter();reasons=collections.Counter();characters=set();started=time.monotonic()
    csvfile=(OUT/'review.csv').open('w',encoding='utf-8-sig',newline='')
    writer=csv.writer(csvfile)
    writer.writerow(['resource_id','fragment_id','source','chinese','status','qa_or_preserve_reason'])
    with DatReader(SOURCE) as reader:
        for entry in reader.entries():
            if entry.resource_id>>24!=0x25:continue
            rid=entry.resource_id;raw=reader.content(entry);source_hash=hashlib.sha256(raw).hexdigest()
            if hashes.pop(rid)!=source_hash:raise ValueError('Source hash mismatch')
            original=TextResource.parse(raw)
            if original.serialize()!=raw:raise ValueError('Original codec roundtrip mismatch')
            translated=copy.deepcopy(original);changed=0
            for left,right in zip(original.fragments,translated.fragments):
                key=(rid,left.identifier);flags=set();reason=''
                if key in overrides:
                    right.pieces=overrides[key];status='existing_translation'
                elif key in preserved:
                    reason=preserved[key];status='preserved';reasons[reason]+=1
                elif re.fullmatch(r'/[A-Za-z][A-Za-z0-9_-]*',''.join(left.pieces).strip()):
                    status='preserved';reason='Executable slash command';reasons[reason]+=1
                elif all(not any('segment' in atom for atom in templates[dumps(p)]) for p in left.pieces):
                    status='preserved';reason='Protocol, URL, selector or numeric content only';reasons[reason]+=1
                else:
                    status='machine_draft'
                    values=[reconstruct(p,templates,segments) for p in left.pieces]
                    right.pieces=[v for v,_ in values]
                    for _,qa in values:flags.update(qa)
                    if right.pieces==left.pieces:
                        status='unchanged_draft';flags.add('unchanged_translation_review')
                validate_fragment(rid,left.pieces,right.pieces)
                counts[status]+=1
                if right.pieces!=left.pieces:changed+=1;counts['changed_fragments']+=1
                if flags:counts['fragments_with_qa_flags']+=1
                if right.pieces!=left.pieces:
                    for piece in right.pieces:characters.update(c for c in piece if 127<ord(c)<=0xffff and not 0xd800<=ord(c)<=0xdfff)
                qa=','.join(sorted(flags)) or reason
                archive.execute('INSERT INTO review VALUES(?,?,?,?,?,?)',
                    (rid,left.identifier,dumps(left.pieces),dumps(right.pieces),status,qa))
                writer.writerow([f'0x{rid:08X}',str(left.identifier),''.join(left.pieces),''.join(right.pieces),status,qa])
            payload=translated.serialize()
            compare_structure(original,TextResource.parse(payload))
            if changed:
                archive.execute('INSERT INTO resources VALUES(?,?,?,?,?)',
                    (rid,source_hash,hashlib.sha256(payload).hexdigest(),payload,changed))
                counts['changed_resources']+=1
            counts['resources']+=1;counts['fragments']+=len(original.fragments)
            if counts['resources']%25000==0:
                archive.commit();csvfile.flush();print('Built resources:',counts['resources'],flush=True)
    if hashes:raise ValueError('Catalog resources missing from source archive')
    csvfile.close()
    summary={'counts':dict(counts),'preservation_reasons':dict(reasons),
             'required_bmp_characters':len(characters),'deployment_enabled':False,'ready_for_install':False,
             'human_review_complete':False,'game_tested':False,'elapsed_seconds':round(time.monotonic()-started,1)}
    archive.execute('INSERT INTO metadata VALUES(?,?)',('summary',json.dumps(summary)))
    archive.commit()
    if archive.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Archive integrity failed')
    archive.close();dest.replace(OUT/'text-resources.sqlite3')
    (OUT/'required-characters.txt').write_text(''.join(sorted(characters)),encoding='utf-8')
    (OUT/'build-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':build()
