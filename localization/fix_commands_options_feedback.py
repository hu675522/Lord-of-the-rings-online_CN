"""Restore command protocol literals and apply source-bound UI corrections."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from localization.build_batch import command_fragment,validate_fragment
from localization.full_translate import connect,dumps

UI_SCOPES={0x250001ff:'graphics',0x250001bc:'options_menu',
           0x250001a7:'chat',0x2500001e:'chat',0x250001bb:'chat',
           0x25012805:'chat_channels'}


def main():
    edits=json.loads((ROOT/'localization/options-feedback-corrections.json').read_text(encoding='utf-8'))
    source=sqlite3.connect(ROOT/'localization/catalog.sqlite3')
    archive=sqlite3.connect(ROOT/'localization/full/text-resources.sqlite3')
    jobs=connect();changes=[];protected=0;seen=set()
    ids=(*UI_SCOPES,0x250001ab)
    for rid,fid,raw in source.execute('SELECT resource_id,id,pieces FROM fragments WHERE resource_id IN ('+','.join('?' for _ in ids)+')',ids):
        before=json.loads(raw)
        old=json.loads(archive.execute('SELECT chinese_pieces FROM review WHERE resource_id=? AND fragment_id=?',(rid,fid)).fetchone()[0])
        after=list(old);reason=None
        if command_fragment(rid,before):
            after=list(before);reason='restore executable command aliases/arguments';protected+=1
            jobs.execute('DELETE FROM overrides WHERE resource_id=? AND fragment_id=?',(rid,fid))
            jobs.execute('INSERT OR REPLACE INTO preserved VALUES(?,?,?)',(rid,fid,'Executable command aliases/arguments; retained unchanged'))
        else:
            mapping=edits[UI_SCOPES[rid]] if rid in UI_SCOPES else {}
            for i,piece in enumerate(before):
                if piece in mapping:
                    after[i]=mapping[piece];reason='reviewed graphics/options/chat wording';seen.add((rid,piece))
            if after!=old:
                jobs.execute('INSERT OR REPLACE INTO overrides VALUES(?,?,?)',(rid,fid,dumps(after)))
        validate_fragment(rid,before,after)
        if after!=old:
            changes.append({'resource_id':f'0x{rid:08X}','fragment_id':fid,'source_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                            'source':before,'previous':old,'target':after,'reason':reason})
    if protected<230 or (0x250001ff,'Scenery') not in seen or (0x250001a7,'IMs') not in seen:
        raise ValueError('Expected command/UI snapshot not found')
    jobs.commit();jobs.close();source.close();archive.close()
    report_path=ROOT/'localization/full/commands-options-feedback-corrections.json'
    history=json.loads(report_path.read_text(encoding='utf-8')).get('changes',[]) if report_path.exists() else []
    merged={(r['resource_id'],r['fragment_id']):r for r in history}
    for change in changes:
        key=(change['resource_id'],change['fragment_id'])
        if key in merged:change['previous']=merged[key]['previous']
        merged[key]=change
    report={'protected_command_fragments':protected,'changed_fragments':len(merged),'deployment_enabled':False,'changes':list(merged.values())}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Protected command fragments:',protected,'changed fragments:',len(changes),flush=True)


if __name__=='__main__':main()
