"""Check the entire reconstruction plan before writing a payload archive."""
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT,connect,dumps
from localization.full_build import reconstruct
from localization.build_batch import validate_pieces,controls,validate_fragment


def main():
    db=connect()
    segments={i:(s,t,status,qa) for i,s,t,status,qa in db.execute('SELECT * FROM segments')}
    templates={s:json.loads(t) for s,t in db.execute('SELECT * FROM pieces')}
    overrides={(r,f):json.loads(p) for r,f,p in db.execute('SELECT * FROM overrides')}
    preserved={(r,f) for r,f in db.execute('SELECT resource_id,fragment_id FROM preserved')}
    problems=[];checked=0
    catalog=sqlite3.connect(BASE/'catalog.sqlite3')
    for rid,fid,raw in catalog.execute('SELECT resource_id,id,pieces FROM fragments'):
        source=json.loads(raw);target=None
        try:
            if (rid,fid) in overrides:target=overrides[rid,fid]
            elif (rid,fid) in preserved:target=source
            else:target=[reconstruct(p,templates,segments)[0] for p in source]
            validate_fragment(rid,source,target)
        except (ValueError,KeyError) as e:
            problems.append({'resource_id':f'0x{rid:08X}','fragment_id':fid,'source':source,'target':target,
                'source_controls':[controls(p) for p in source],
                'target_controls':[controls(p) for p in target] if target else None,'error':str(e)})
        checked+=1
    report={'checked_fragments':checked,'problems':problems,'deployment_enabled':False}
    (OUT/'preflight.json').write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='utf-8')
    print('Preflight fragments:',checked,'problems:',len(problems),flush=True)
    for problem in problems[:10]:print({k:problem[k] for k in ('resource_id','fragment_id','source_controls','target_controls')},flush=True)
    if problems:raise ValueError('Preflight errors must be resolved before build')


if __name__=='__main__':main()
