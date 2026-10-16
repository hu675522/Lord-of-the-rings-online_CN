"""Sentence-by-sentence pass to prevent premature EOS on narrative paragraphs."""
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import OUT,connect,engine,normalize_input,cut_text
from localization.full_quality import flags_for,audit


def split_sentences(text):
    return re.split(r'(?<=[.!?])(?=\s)',text)


def main():
    db=connect()
    db.execute('CREATE TABLE IF NOT EXISTS sentence_pass(id INTEGER PRIMARY KEY,parts TEXT,status TEXT)')
    if not db.execute("SELECT 1 FROM metadata WHERE key='sentence_plan'").fetchone():
        added=0
        for sid,source,qa in db.execute("SELECT id,source,qa FROM segments WHERE status='machine_draft'").fetchall():
            sentences=split_sentences(source)
            flagged=any(x in qa for x in ('compression_review','omission_review'))
            if len(sentences)<2 and not flagged:continue
            parts=[p for sentence in sentences for p in cut_text(sentence,limit=100 if flagged else 180)]
            db.execute('INSERT OR IGNORE INTO sentence_pass VALUES(?,?,?)',(sid,json.dumps(parts),'pending'));added+=1
        db.execute('INSERT INTO metadata VALUES(?,?)',('sentence_plan',str(added)));db.commit()
        print('Sentence refinement units:',added,flush=True)
    translator,sp,tp,handles=engine('ct2-int8-filtered')
    completed=0
    while True:
        rows=db.execute("SELECT p.id,p.parts,s.source FROM sentence_pass p JOIN segments s ON s.id=p.id WHERE p.status='pending' LIMIT 128").fetchall()
        if not rows:break
        inputs=[];owners=[];edges=[]
        for index,(_,raw,_) in enumerate(rows):
            for part in json.loads(raw):
                left,body,right=re.fullmatch(r'(\s*)(.*?)(\s*)',part,flags=re.S).groups()
                if not body:continue
                # Initial quotation marks and exclamation punctuation remain
                # outside the model, where they cannot trigger early EOS.
                leading,body,trailing=re.fullmatch(r'([\'".!?…]*)(.*?)([\'".!?…]*)',body,flags=re.S).groups()
                if not body:body=leading+trailing;leading=trailing=''
                owners.append(index);edges.append((left+leading,trailing+right))
                inputs.append(['>>cmn_Hans<<']+sp.encode(normalize_input(body),out_type=str))
        results=translator.translate_batch(inputs,beam_size=2,max_batch_size=4096,batch_type='tokens',
            max_decoding_length=256,disable_unk=True,no_repeat_ngram_size=3)
        values=['']*len(rows);truncated=set()
        for result,index,(left,right) in zip(results,owners,edges):
            values[index]+=left+tp.decode(result.hypotheses[0]).strip()+right
            if len(result.hypotheses[0])>=256:truncated.add(index)
        for index,(sid,_,source) in enumerate(rows):
            target=values[index]
            if re.search(r'\bquests?\b',source,re.I):target=target.replace('探险任务','任务').replace('探险','任务')
            flags=flags_for(source,target)
            if index in truncated or 'invalid_output' in flags or 'unexpected_script' in flags:
                db.execute("UPDATE sentence_pass SET status='retained_previous_draft' WHERE id=?",(sid,))
            else:
                db.execute('UPDATE segments SET translation=?,qa=? WHERE id=?',(target,','.join(flags),sid))
                db.execute("UPDATE sentence_pass SET status='complete' WHERE id=?",(sid,))
        db.commit();completed+=len(rows)
        if completed%4096==0:print('Sentence pass processed:',completed,flush=True)
    corrections={
        's CD)':'秒冷却)',', & SItS':'，以及 SItS',
        "'Oh! Oh... I...'":"哦！哦……我……",
        "'The horn sounded to the east of Skarháld. I think that is where you will find them.'":'号角声从斯卡哈尔德（Skarháld）以东传来。我想你能在那里找到他们。',
        'Quick-handed':'手脚敏捷',"'Flee! We must flee, precious!'":'快逃！我们必须逃走，宝贝！',
    }
    db.executemany("UPDATE segments SET translation=?,status='reviewed_correction',qa='' WHERE source=?",[(t,s) for s,t in corrections.items()])
    # These are generator syllables, not player-visible prose. Translating the
    # individual sound fragments would change the name-generation grammar.
    with __import__('sqlite3').connect(OUT.parent/'catalog.sqlite3') as catalog:
        for fid, in catalog.execute('SELECT id FROM fragments WHERE resource_id=?',(0x2501a9c0,)):
            db.execute('INSERT OR REPLACE INTO preserved VALUES(?,?,?)',(0x2501a9c0,fid,'Name-generation syllables; preserved'))
    counts=audit(db)
    report={'sentence_pass':dict(db.execute('SELECT status,count(*) FROM sentence_pass GROUP BY status')),
            'quality_flags':dict(counts),'segment_statuses':dict(db.execute('SELECT status,count(*) FROM segments GROUP BY status')),
            'human_review_complete':False,'deployment_enabled':False}
    (OUT/'sentence-refinement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    db.close()


if __name__=='__main__':main()
