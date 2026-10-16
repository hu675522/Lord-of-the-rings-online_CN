"""Apply explicit editorial corrections and audited technical preservation."""
import collections
import json
from pathlib import Path
import re
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT,connect
from localization.full_quality import audit


def main():
    db=connect()
    corrections=json.loads((BASE/'full_corrections.json').read_text(encoding='utf-8'))
    for sid,target in corrections.items():
        if not db.execute('SELECT 1 FROM segments WHERE id=?',(int(sid),)).fetchone():raise ValueError('Correction unit missing')
        db.execute("UPDATE segments SET translation=?,status='reviewed_correction',qa='' WHERE id=?",(target,int(sid)))
    # Mark every fragment of the audited lowercase sound-component tables.
    catalog=sqlite3.connect(BASE/'catalog.sqlite3')
    groups=collections.defaultdict(list)
    for rid,fid,raw in catalog.execute('SELECT resource_id,id,pieces FROM fragments'):
        groups[rid].append((fid,json.loads(raw)))
    names=[];internal=0;cipher=0
    ciphertext={208511,208512}
    cipher_sources={s for sid,s in db.execute('SELECT id,source FROM segments') if sid in ciphertext}
    for rid,fragments in groups.items():
        if len(fragments)>=10 and all(len(p)==1 and re.fullmatch('[a-z]{1,8}',p[0]) for _,p in fragments):
            names.append({'resource_id':f'0x{rid:08X}','fragments':len(fragments)})
            for fid,_ in fragments:db.execute('INSERT OR REPLACE INTO preserved VALUES(?,?,?)',(rid,fid,'Name-generation syllables; preserved'))
        for fid,pieces in fragments:
            joined=''.join(pieces)
            if re.fullmatch(r'ID_[A-Za-z0-9_]+',joined):
                db.execute('INSERT OR REPLACE INTO preserved VALUES(?,?,?)',(rid,fid,'Internal interface identifier; preserved'));internal+=1
            elif any(source in joined for source in cipher_sources):
                db.execute('INSERT OR REPLACE INTO preserved VALUES(?,?,?)',(rid,fid,'Ciphertext/puzzle letter sequence; preserved'));cipher+=1
    for sid in [208511,208512,245364,415708,557161,557209]:
        db.execute("UPDATE segments SET translation=source,status='technical_preserved',qa='' WHERE id=?",(sid,))
    db.commit();qa=audit(db)
    report={'editorial_corrections':len(corrections),'sound_component_tables':names,
            'internal_identifier_fragments':internal,'ciphertext_fragments':cipher,'remaining_auto_flags':dict(qa),
            'human_review_complete':False,'deployment_enabled':False}
    (OUT/'editorial-corrections.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    db.close();catalog.close()


if __name__=='__main__':main()
