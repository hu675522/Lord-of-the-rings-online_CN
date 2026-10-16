"""Independently verify every exported resource against the English backup."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT
from localization.build_batch import SOURCE,validate_pieces,validate_fragment,command_fragment
from lotro_zh.dat_reader import DatReader
from lotro_zh.text_resource import TextResource


def verify():
    archive=sqlite3.connect(OUT/'text-resources.sqlite3')
    catalog=sqlite3.connect(BASE/'catalog.sqlite3')
    resources={r:(s,p) for r,s,p in archive.execute('SELECT id,source_sha256,payload_sha256 FROM resources')}
    expected=dict(catalog.execute('SELECT id,sha256 FROM resources'))
    checked=Counter()
    if archive.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failed')
    with DatReader(SOURCE) as reader:
        for entry in reader.entries():
            rid=entry.resource_id
            if rid>>24!=0x25:continue
            original=reader.content(entry);source_hash=hashlib.sha256(original).hexdigest()
            if expected.pop(rid)!=source_hash:raise ValueError('Catalog/source mismatch')
            left=TextResource.parse(original)
            if rid in resources:
                source_expected,payload_hash=resources.pop(rid)
                payload=archive.execute('SELECT payload FROM resources WHERE id=?',(rid,)).fetchone()[0]
                if source_expected!=source_hash or hashlib.sha256(payload).hexdigest()!=payload_hash:
                    raise ValueError('Payload/source hash mismatch')
                right=TextResource.parse(payload)
                if right.serialize()!=payload:raise ValueError('Payload roundtrip mismatch')
                checked['changed_resources']+=1
            else:right=left
            if (left.identifier,left.unknown,left.trailing,len(left.fragments))!=(right.identifier,right.unknown,right.trailing,len(right.fragments)):
                raise ValueError('Resource framing mismatch')
            review={f:(json.loads(s),json.loads(t)) for f,s,t in archive.execute(
                'SELECT fragment_id,source_pieces,chinese_pieces FROM review WHERE resource_id=?',(rid,))}
            for before,after in zip(left.fragments,right.fragments):
                if (before.identifier,before.arg_refs,before.arg_strings)!=(after.identifier,after.arg_refs,after.arg_strings):
                    raise ValueError('Argument mismatch')
                validate_fragment(rid,before.pieces,after.pieces)
                if command_fragment(rid,before.pieces):checked['executable_command_fragments']+=1
                if review.pop(before.identifier)!=(before.pieces,after.pieces):raise ValueError('Review/payload mismatch')
                checked['fragments']+=1
            if review:raise ValueError('Unexpected review fragments')
            checked['all_resources']+=1
            if checked['all_resources']%50000==0:print('Independently verified:',checked['all_resources'],flush=True)
    if resources or expected:raise ValueError('Missing resources')
    jobs=sqlite3.connect(OUT/'jobs.sqlite3')
    counts=dict(jobs.execute('SELECT status,count(*) FROM segments GROUP BY status'))
    if counts.get('pending',0) or counts.get('error',0):raise ValueError('Unfinished translation jobs')
    policy=json.loads((BASE.parent/'client_patch/deployment-policy.json').read_text(encoding='utf-8'))
    if policy.get('deployment_enabled') is not False:raise ValueError('Deployment lock changed')
    report={'verified':dict(checked),'segment_statuses':counts,'source_hashes_verified':True,
        'all_resource_roundtrips_verified':True,'all_dynamic_arguments_preserved':True,
        'all_markup_and_piece_boundaries_preserved':True,'review_matches_binary_payloads':True,
        'deployment_enabled':False,'game_tested':False,'human_review_complete':False}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':verify()
