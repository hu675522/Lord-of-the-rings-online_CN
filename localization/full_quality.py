"""Flag suspicious drafts and retry failed outputs; never marks them reviewed."""
import collections
import json
from pathlib import Path
import re
import sys
import unicodedata
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import OUT,connect,engine,HAN,controls,normalize_input,cut_text


def flags_for(source,target):
    flags=[]
    if not target or controls(target) or any(unicodedata.category(c)=='Co' for c in target):flags.append('invalid_output')
    if not HAN.search(target):flags.append('no_han_or_proper_name')
    if re.search(r'([\u3400-\u9fff]{2,10})\1{2,}',target):flags.append('repetition_review')
    if len(target)>max(30,len(source)*1.5):flags.append('expansion_review')
    if len(re.findall('[A-Za-z]+',source))>=8 and len(HAN.findall(target))<4:flags.append('omission_review')
    if len(source)>100 and len(HAN.findall(target))+len(re.findall('[A-Za-z]',target))*.5<len(source)*.15:
        flags.append('compression_review')
    if any(c.isalpha() and not HAN.fullmatch(c) and 'LATIN' not in unicodedata.name(c,'')
           and c not in source for c in target):
        flags.append('unexpected_script')
    return flags


def audit(db):
    updates=[];counts=collections.Counter()
    for sid,source,target,status,qa in db.execute("SELECT * FROM segments WHERE status IN ('machine_draft','error')"):
        flags=flags_for(source,target or '')
        if 'possible_truncation' in qa:flags.append('possible_truncation')
        counts.update(flags)
        updates.append((','.join(flags),sid))
    db.executemany('UPDATE segments SET qa=? WHERE id=?',updates);db.commit()
    return counts


def main():
    db=connect()
    if db.execute("SELECT count(*) FROM segments WHERE status='pending'").fetchone()[0]:raise ValueError('Translation still running')
    before=audit(db)
    # Retry all flagged outputs with a wider beam and punctuation kept outside
    # the model. Normal-looking drafts stay checkpointed and unchanged.
    rows=db.execute("SELECT id,source,translation,qa FROM segments WHERE qa!='' AND status IN ('machine_draft','error')").fetchall()
    print('Flagged units before retry:',dict(before),'units',len(rows),flush=True)
    translator,sp,tp,handles=engine('ct2-int8-filtered')
    improved=0
    for start in range(0,len(rows),64):
        batch=rows[start:start+64];inputs=[];edges=[];owners=[]
        for index,(_,source,_,_) in enumerate(batch):
            for span in cut_text(source,limit=140):
                match=re.fullmatch(r'([\s.,!?\'"…:;-]*)(.*?)([\s.,!?\'"…:;-]*)',span,flags=re.S)
                left,body,right=match.groups();edges.append((left,right));owners.append(index)
                inputs.append(['>>cmn_Hans<<']+sp.encode(normalize_input(body or span),out_type=str))
        outputs=translator.translate_batch(inputs,beam_size=4,max_batch_size=2048,batch_type='tokens',
            max_decoding_length=384,disable_unk=True,no_repeat_ngram_size=3,repetition_penalty=1.1)
        values=['']*len(batch);truncated=set()
        for result,(left,right),index in zip(outputs,edges,owners):
            values[index]+=left+tp.decode(result.hypotheses[0]).strip()+right
            if len(result.hypotheses[0])>=384:truncated.add(index)
        for index,(sid,source,old,oldqa) in enumerate(batch):
            value=values[index]
            if re.search(r'\bquests?\b',source,re.I):value=value.replace('探险任务','任务').replace('探险','任务')
            flags=flags_for(source,value)
            if index in truncated:flags.append('possible_truncation')
            weights={'invalid_output':100,'possible_truncation':100,'unexpected_script':20,'no_han_or_proper_name':10}
            score=lambda fs:sum(weights.get(f,1) for f in fs)
            if score(flags)<score(oldqa.split(',')) or not flags:
                db.execute("UPDATE segments SET translation=?,status='machine_draft',qa=? WHERE id=?",(value,','.join(flags),sid));improved+=1
        db.commit()
        if start%512==0:print('Quality retry:',start+len(batch),'/',len(rows),flush=True)
    after=audit(db)
    report={'machine_quality_review_complete':False,'flagged_before':dict(before),'flagged_after':dict(after),
            'retry_units':len(rows),'improved_units':improved,'deployment_enabled':False}
    (OUT/'quality-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'quality-segments.jsonl').open('w',encoding='utf-8') as file:
        for sid,source,target,status,qa in db.execute("SELECT * FROM segments WHERE qa!=''"):
            file.write(json.dumps({'id':sid,'source':source,'chinese':target,'status':status,'qa':qa},ensure_ascii=False)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    db.close()


if __name__=='__main__':main()
