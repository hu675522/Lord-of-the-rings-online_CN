"""Audit this exact English runtime snapshot before the 0.1.3 local test.

No live writes. One already observed server-updated item record is excluded
from translation; all other catalog text and replacement font/map sources must
still match. Opaque untouched resources are preserved from this pinned snapshot.
"""
import json
from pathlib import Path
import sqlite3
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from client_patch.full_manager import file_hash,write_json,require_closed
from lotro_zh.dat_reader import DatReader

CURRENT='aaa329a3835d3de314ca5b82cfb87da685a0ec7d5af32910ff51d9a2d9d008cb'
CURRENT_ARCHIVES={
    'client_local_English.dat':CURRENT,
    'client_surface.dat':'405e50e3e5ea4572c70958e1bac85b4fbca75be79af96831177a4c587fee692e',
    'client_surface_aux_1.datx':'8fba5209f1c6f65ebf3b74765a10225fc9576c321aa0869bf1d2cd5fa196ac9e',
    'client_surface_aux_2.datx':'c9f3465fda511f8f3a674f3c8eebadfec733d3942b932db6ff4bf46f30f1e207',
    'client_general.dat':'bc02b2d243274e0751c96a346f881fc8d966d726b6e64d76b94107367ccb8f26'}
CACHE_ID=0x2505ba52
CACHE_HASH='a355de876042806c28e39b7eeae346217abd89ae1282118fd307cad2b8076dad'


def main():
    require_closed()
    config=json.loads((ROOT/'data/original-archives.json').read_text(encoding='utf-8'))
    game=Path(config['game_directory']);archives={}
    for name,info in config['archives'].items():
        p=game/name;digest=file_hash(p)
        expected=CURRENT_ARCHIVES[name]
        if digest!=expected or p.stat().st_size!=info['bytes']:raise ValueError('Unexpected source snapshot: '+name)
        archives[name]={'original_sha256':digest,'original_size':p.stat().st_size,'previous_sha256':info['sha256']}
        print('Pinned source verified:',name,flush=True)
    if file_hash(game/'x64/lotroclient64.exe')!='d131a79b23beaf580221df60c6308e339b72bfb93b39b2817b3d51828a8c39f2':
        raise ValueError('Unexpected client version')
    # CACHE_ID/CACHE_HASH pin the already identified server-updated item.
    # The full source/resource checks below do not depend on private test logs.
    db=sqlite3.connect((ROOT/'localization/catalog.sqlite3').as_uri()+'?mode=ro',uri=True)
    expected=dict(db.execute('SELECT id,sha256 FROM resources'));db.close()
    fonts=json.loads((ROOT/'localization/full/fonts/manifest.json').read_text(encoding='utf-8'))
    extra={r['id']:r['source_sha256'] for r in fonts['records'] if r['group']=='client_local_English.dat'}
    maps_path=ROOT/'localization/maps/bilingual-draft/manifest.json'
    maps=json.loads(maps_path.read_text(encoding='utf-8'))
    extra.update({r['id']:r['source_sha256'] for r in maps['records']})
    verified=0;changed=[];extras=0
    with DatReader(game/'client_local_English.dat') as reader:
        entries={e.resource_id:e for e in reader.entries()}
        public={r for r in entries if r<0xff000000}
        if len(public)!=311966:raise ValueError('Public resource count changed')
        if set(expected)!={r for r in entries if r>>24==0x25}:raise ValueError('Text resource ID set changed')
        for rid,digest in expected.items():
            current=file_hash_bytes(reader.content(entries[rid]))
            if current!=digest:
                if rid!=CACHE_ID or current!=CACHE_HASH:raise ValueError('Unexpected text change: '+hex(rid))
                changed.append({'id':hex(rid),'previous_sha256':digest,'current_sha256':current})
            else:verified+=1
            if (verified+len(changed))%50000==0:print('Catalog text checked:',verified+len(changed),flush=True)
        for rid,digest in extra.items():
            if file_hash_bytes(reader.content(entries[rid]))!=digest:raise ValueError('Font/map source changed')
            extras+=1
    if len(changed)!=1 or verified!=282189:raise ValueError('Unexpected audit coverage')
    for group,names,count in [
        ('client_surface.dat group',['client_surface.dat','client_surface_aux_1.datx','client_surface_aux_2.datx'],1329898),
        ('client_general.dat',['client_general.dat'],261505)]:
        wanted={r['id']:r['source_sha256'] for r in fonts['records'] if r['group']==group}
        seen=set()
        for name in names:
            with DatReader(game/name) as reader:
                for entry in reader.entries():
                    rid=entry.resource_id
                    if rid<0xff000000:
                        if rid in seen:raise ValueError('Duplicate public resource')
                        seen.add(rid)
                    if rid in wanted:
                        if file_hash_bytes(reader.content(entry))!=wanted.pop(rid):raise ValueError('Font/texture source changed')
                        extras+=1
        if wanted or len(seen)!=count:raise ValueError('Source group IDs/count mismatch')
        print('Font/texture sources and group count verified:',group,flush=True)
    require_closed()
    for name,row in archives.items():
        if file_hash(game/name)!=row['original_sha256']:raise ValueError('Source changed during audit')
    report={'kind':'exact-english-runtime-window-test','audited_utc':datetime.now(timezone.utc).isoformat(),
        'game_directory':str(game),'source_archives':archives,'text_resources_checked':282190,
        'matching_text_resources':verified,'public_resources':311966,'changed_text_resources':changed,
        'font_map_source_resources_checked':extras,'exclude_resource_ids':[CACHE_ID],
        'source_manifest_sha256':file_hash(ROOT/'localization/full/manifest.json'),
        'map_manifest_sha256':file_hash(maps_path),'all_other_catalog_text_matches':True,
        'note':'Untouched records are retained from the current pinned English snapshot; historical full-file or opaque-resource equality is not claimed.',
        'live_game_modified':False}
    write_json(ROOT/'artifacts/map-research/window-test-source-audit.json',report)
    print('Exact English source audited; one runtime record will remain unchanged.',flush=True)


def file_hash_bytes(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


if __name__=='__main__':main()
