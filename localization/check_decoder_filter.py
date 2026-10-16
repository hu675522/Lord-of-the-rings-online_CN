import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT,engine,connect,bad_decoder_token,normalize_input

db=connect()
rows=db.execute("SELECT source FROM segments WHERE length(source)>20 ORDER BY id LIMIT 256").fetchall()
samples=['she','her','You completed the quest.','Gather fresh bandages for Zâgsha.','Zímarp']+[r[0] for r in rows]
vocab=json.loads((BASE/'models/opus-en-zh/ct2-int8/shared_vocabulary.json').read_text(encoding='utf-8'))
report={}
values=[]
for name in ('ct2-int8','ct2-int8-filtered'):
    translator,source,target,handles=engine(name)
    start=time.monotonic()
    tokens=[['>>cmn_Hans<<']+source.encode(normalize_input(s),out_type=str) for s in samples]
    kwargs={} if name.endswith('filtered') else {'suppress_sequences':[[t] for t in vocab if bad_decoder_token(t)]}
    results=translator.translate_batch(tokens,beam_size=1,max_batch_size=4096,batch_type='tokens',
        max_input_length=512,max_decoding_length=384,disable_unk=True,no_repeat_ngram_size=4,**kwargs)
    output=[target.decode(r.hypotheses[0]) for r in results]
    values.append(output)
    report[name]={'seconds':round(time.monotonic()-start,3),'examples':list(zip(samples[:5],output[:5]))}
    translator.unload_model();del translator
report['identical_outputs']=values[0]==values[1]
report['comparison_segments']=len(samples)
(OUT/'decoder-filter-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
if not report['identical_outputs']:raise RuntimeError('Decoder constraints differ')
