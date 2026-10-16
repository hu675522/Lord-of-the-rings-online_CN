"""Export source-bound Chinese aliases to English singular names, offline only."""
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'localization/full/text-resources.sqlite3'
OUT=ROOT/'localization/item_lookup/generated'
NAME_ID=228870261
PLURAL_ID=98907573
sys.path.insert(0,str(ROOT))
from localization.item_lookup.layout import DESCRIPTOR,validate_layout


def clean(text):
    text=re.sub(r'<[^>]*>','',text)
    return re.sub(r'\[[A-Za-z!0-9]+\]$','',text).strip()


def normalize_alias(text):
    text=text.replace('\ufeff','').replace('\u200b','').replace('\xa0',' ').replace('\u3000',' ')
    return re.sub(r'[ \t\r\n\v\f]+',' ',text).strip()


def lua_string(text):
    # Lua 5.1 does not understand JSON's \u escapes. Preserve UTF-8 and use
    # its supported decimal escapes for controls, plus ordinary quotes.
    return '"'+''.join('\\'+c if c in '\\"' else f'\\{ord(c):03d}' if ord(c)<32 else c for c in text)+'"'


def lua_ascii_string(text):
    # All dictionary source bytes are ASCII; Lua reconstructs exact UTF-8 keys.
    return '"'+''.join('\\'+chr(b) if b in (34,92) else f'\\{b:03d}' if b<32 or b>=127 else chr(b)
                       for b in text.encode('utf-8'))+'"'


def add_resource(index,rows):
    singular=rows.get(NAME_ID)
    if not singular:return 0
    source,target=singular
    if len(source)!=1 or len(target)!=1:return 0
    english=clean(source[0])
    if not english or any(c in english for c in '\\{}|<>') or len(english)>240:return 0
    added=0
    for fid in (NAME_ID,PLURAL_ID):
        if fid not in rows:continue
        originals,translated=rows[fid]
        if len(originals)!=1 or len(translated)!=1:continue
        alias=normalize_alias(clean(translated[0]))
        if not re.search(r'[\u3400-\u9fff]',alias) or any(c in alias for c in '\\{}|<>'):continue
        index[alias].add(english); added+=1
    return added


def main():
    db=sqlite3.connect(SOURCE.as_uri()+'?mode=ro',uri=True)
    index=collections.defaultdict(set); rows={};previous=None;resources=0
    for rid,fid,source,target in db.execute('SELECT resource_id,fragment_id,source_pieces,chinese_pieces FROM review WHERE fragment_id IN (?,?) ORDER BY resource_id,fragment_id',(NAME_ID,PLURAL_ID)):
        if previous is not None and rid!=previous:
            resources+=bool(add_resource(index,rows));rows={}
        previous=rid;rows[fid]=(json.loads(source),json.loads(target))
    if rows:resources+=bool(add_resource(index,rows))
    db.close()
    plugin=OUT/'Plugins/LotroZh/ItemEnglish';data=plugin/'Data';data.mkdir(parents=True,exist_ok=True)
    shards=collections.defaultdict(dict)
    for alias,options in index.items():
        prefix=alias.encode('utf-8')[:2].hex().upper()
        shards[prefix][alias]=sorted(options)
    records=[]
    for prefix,entries in sorted(shards.items()):
        file=data/f'Shard_{prefix}.lua'
        text='_G.LotroZhItemEnglishShards = _G.LotroZhItemEnglishShards or {};\n_G.LotroZhItemEnglishShards['+lua_ascii_string(prefix)+'] = {\n'+''.join(f'[{lua_ascii_string(a)}] = {{'+','.join(lua_ascii_string(e) for e in entries[a])+'},\n' for a in sorted(entries))+'}\n'
        file.write_text(text,encoding='utf-8');raw=file.read_bytes()
        records.append({'file':file.relative_to(OUT).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'aliases':len(entries)})
    source_folder=ROOT/'localization/item_lookup/plugin'
    for name in ('Main.lua','Lookup.lua'):
        if name=='Lookup.lua':
            text=(source_folder/name).read_text(encoding='utf-8')
            marker='api.available_shards = nil;'
            if text.count(marker)!=1:raise ValueError('Lookup shard marker changed')
            text=text.replace(marker,'api.available_shards = {'+','.join('['+lua_ascii_string(p)+']=true' for p in sorted(shards))+'};')
            (plugin/name).write_text(text,encoding='utf-8')
        else:shutil.copyfile(source_folder/name,plugin/name)
    # Remove only our obsolete root descriptor from previous generated exports.
    legacy=OUT/'Plugins/LotroZhItemEnglish.plugin'
    if legacy.exists():
        import xml.etree.ElementTree as ET
        if ET.parse(legacy).getroot().findtext('Package')!='LotroZh.ItemEnglish.Main':
            raise ValueError('Unexpected legacy descriptor; preserved')
        legacy.unlink()
    shutil.copyfile(source_folder/'LotroZhItemEnglish.plugin',OUT/DESCRIPTOR)
    layout=validate_layout(OUT)
    for file in [plugin/'Main.lua',plugin/'Lookup.lua',OUT/DESCRIPTOR]:
        raw=file.read_bytes()
        records.append({'file':file.relative_to(OUT).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    report={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'name_resources_indexed':resources,
        'chinese_aliases':len(index),'ambiguous_aliases':sum(len(v)>1 for v in index.values()),
        'shards':len(shards),'game_tested':False,'installed':False,'records':records,'layout':layout,
        'shard_encoding':'ASCII Lua source with decimal UTF-8 byte escapes','shard_storage':'persistent global registry',
        'note':'Name-fragment index also contains non-item titles. Exact drag/drop names and ambiguity selection are required.'}
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for alias in ['银片大片','银碎片的堆积','银渣大堆']:
        print(alias,sorted(index.get(alias,[])))
    print({k:v for k,v in report.items() if k!='records'})


if __name__=='__main__':main()
