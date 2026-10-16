"""Checkpointed offline full-catalog machine draft. Never deploys game files."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import unicodedata

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
OUT=BASE/'full'
sys.path.insert(0,str(ROOT))
from localization.build_batch import controls,validate_pieces,preserve_reason,command_fragment

# Split protocol atoms away from the model instead of asking it to reproduce
# them. Grammar branch words remain translatable, selectors remain byte-exact.
ATOM=re.compile(r'https?://[^\s<>]+|<[^>]*>|<[A-Za-z][A-Za-z0-9_]*:[^<>]*$|^>$|\\+.|\[[^\[\]]*\]|#-?\d+:|%[-+0-9.]*[sdf]|(?<![\w/])/[A-Za-z][A-Za-z0-9_-]*|[{}|#%]|\d+(?:[.,]\d+)*(?:%|)')
LATIN=re.compile('[A-Za-z]')
HAN=re.compile('[\u3400-\u9fff]')


def bad_decoder_token(token):
    if token in {'</s>','<s>','<pad>','<unk>'}:return False
    return any(unicodedata.category(c)=='Co' or c in '{}|\\<>' or
               (0x2500<=ord(c)<=0x259f and c!='▁') or 0x3100<=ord(c)<=0x312f or
               (c.isalpha() and not HAN.fullmatch(c) and 'LATIN' not in unicodedata.name(c,'')) for c in token)


def normalize_input(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c))


def configure_decoder(db):
    revision='protected-hans-v2'
    previous=db.execute("SELECT value FROM metadata WHERE key='decoder_revision'").fetchone()
    if previous and previous[0]==revision:return
    db.execute('CREATE TABLE IF NOT EXISTS rejected_decoder_revision(id INTEGER PRIMARY KEY,translation TEXT,status TEXT,qa TEXT)')
    db.execute("INSERT OR REPLACE INTO rejected_decoder_revision SELECT id,translation,status,qa FROM segments WHERE status IN ('machine_draft','error')")
    db.execute("UPDATE segments SET translation=NULL,status='pending',qa='' WHERE status IN ('machine_draft','error')")
    memory={'she':'她','She':'她','her':'她','Her':'她','he':'他','He':'他','him':'他','Him':'他',
            'his':'他的','His':'他的','their':'他们的','Their':'他们的',
            'This item is bound to your account.':'此物品与你的账号绑定。'}
    rows=json.loads((BASE/'output/batch-001/review.json').read_text(encoding='utf-8'))
    options={}
    for row in rows:
        if len(row['source_pieces'])!=1:continue
        source,target=row['source_pieces'][0],row['chinese_pieces'][0]
        marker=re.search(r'\[[A-Za-z]+\]$',source)
        if marker and target.endswith(marker[0]):source,target=source[:-len(marker[0])],target[:-len(marker[0])]
        if controls(source) or controls(target) or not source.strip():continue
        options.setdefault(source.strip(),set()).add(target.strip())
    memory.update({s:next(iter(v)) for s,v in options.items() if len(v)==1})
    db.executemany("UPDATE segments SET translation=?,status='glossary',qa='' WHERE source=?",
                   [(t,s) for s,t in memory.items()])
    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('decoder_revision',revision))
    db.commit()
    print('Decoder revision configured; unsupported outputs quarantined and translation memory refreshed.',flush=True)


def dumps(value):return json.dumps(value,ensure_ascii=True,separators=(',',':'))


def connect():
    OUT.mkdir(exist_ok=True)
    db=sqlite3.connect(OUT/'jobs.sqlite3',timeout=60)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS segments(id INTEGER PRIMARY KEY,source TEXT UNIQUE NOT NULL,
        translation TEXT,status TEXT NOT NULL DEFAULT 'pending',qa TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS pieces(source_json TEXT PRIMARY KEY,template TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS overrides(resource_id INTEGER,fragment_id INTEGER,pieces TEXT,
        PRIMARY KEY(resource_id,fragment_id));
      CREATE TABLE IF NOT EXISTS preserved(resource_id INTEGER,fragment_id INTEGER,reason TEXT,
        PRIMARY KEY(resource_id,fragment_id));
      CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
      CREATE INDEX IF NOT EXISTS segments_pending_length ON segments(status,length(source),id);
    ''')
    return db


def cut_text(text,limit=300):
    """Bound model input without dropping any character from the source plan."""
    while len(text)>limit:
        point=max(text.rfind('. ',0,limit),text.rfind('! ',0,limit),text.rfind('? ',0,limit))
        if point>=limit//3:point+=1
        else:point=text.rfind(' ',0,limit)
        if point<limit//3:point=limit
        yield text[:point];text=text[point:]
    if text:yield text


def plan_piece(piece,resolve):
    result=[]
    def span(text):
        for part in cut_text(text):
            leading,body,trailing=re.fullmatch(r'(\s*)(.*?)(\s*)',part,flags=re.S).groups()
            if leading:result.append({'keep':leading})
            if body:result.append({'segment':resolve(body)} if LATIN.search(body) else {'keep':body})
            if trailing:result.append({'keep':trailing})
    start=0
    for token in ATOM.finditer(piece):
        span(piece[start:token.start()]);result.append({'keep':token[0]});start=token.end()
    span(piece[start:])
    return result


def refresh_templates():
    db=connect()
    segments=dict(db.execute('SELECT source,id FROM segments'))
    old_count=len(segments);changed=0
    def resolve(body):
        if body not in segments:
            segments[body]=db.execute('INSERT INTO segments(source) VALUES(?)',(body,)).lastrowid
        return segments[body]
    rows=db.execute('SELECT source_json,template FROM pieces').fetchall()
    for source,old in rows:
        new=dumps(plan_piece(json.loads(source),resolve))
        if new!=old:
            db.execute('UPDATE pieces SET template=? WHERE source_json=?',(new,source));changed+=1
    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('template_revision','numeric-command-multiescape-v3'))
    db.commit();db.close()
    print('Templates refreshed:',changed,'; added units:',len(segments)-old_count,flush=True)


def technical(pieces,resource_id=None):
    if command_fragment(resource_id,pieces):return 'Executable command aliases/arguments; retained unchanged'
    reason=preserve_reason(pieces)
    if reason:return reason
    joined=''.join(pieces)
    if not LATIN.search(joined):return 'No English text'
    if any('\ud800'<=c<='\udfff' for c in joined):return 'Encoded surrogate/control data'
    if re.fullmatch(r'[A-Za-z]:[\\/].*',joined) or re.fullmatch(r'[\w./\\-]+\.(?:lua|dds|tga|jpg|wav|ogg|xml|dat)',joined):
        return 'Internal file path'
    return None


def prepare():
    db=connect()
    existing=db.execute("SELECT value FROM metadata WHERE key='prepared'").fetchone()
    if existing:return
    # Approved/context-specific drafts always take priority over machine output.
    previous=json.loads((BASE/'output/batch-001/review.json').read_text(encoding='utf-8'))
    for item in previous:
        db.execute('INSERT OR REPLACE INTO overrides VALUES(?,?,?)',
                   (int(item['resource_id'],16),int(item['fragment_id']),dumps(item['chinese_pieces'])))
    for name in ('finding-amdir.json','madness-at-damudur.json'):
        plan=json.loads((ROOT/'client_patch/translations'/name).read_text(encoding='utf-8'))
        for fid,pieces in plan['fragments'].items():
            db.execute('INSERT OR REPLACE INTO overrides VALUES(?,?,?)',(int(plan['resource_id'],16),int(fid),dumps(pieces)))
    memory={}
    for name in ('ui-terms.json','ui-common.json','ui-more-pieces.json','ui-housing.json'):
        for source,target in json.loads((BASE/name).read_text(encoding='utf-8')).items():
            if LATIN.search(source) and source.strip()==source and source!=target and controls(source)==controls(target):
                memory[source]=target
    segments={row[0]:row[1] for row in db.execute('SELECT source,id FROM segments')}
    seen={row[0] for row in db.execute('SELECT source_json FROM pieces')}
    def plan_span(text):
        if not text:return []
        if not LATIN.search(text):return [{'keep':text}]
        result=[]
        for part in cut_text(text):
            match=re.fullmatch(r'(\s*)(.*?)(\s*)',part,flags=re.S)
            leading,body,trailing=match.groups()
            if leading:result.append({'keep':leading})
            if body:
                if not LATIN.search(body):result.append({'keep':body})
                else:
                    if body not in segments:
                        value=memory.get(body)
                        cur=db.execute('INSERT INTO segments(source,translation,status) VALUES(?,?,?)',
                                       (body,value,'glossary' if value is not None else 'pending'))
                        segments[body]=cur.lastrowid
                    result.append({'segment':segments[body]})
            if trailing:result.append({'keep':trailing})
        return result
    count=0
    with sqlite3.connect(BASE/'catalog.sqlite3') as catalog:
        for rid,fid,raw in catalog.execute('SELECT resource_id,id,pieces FROM fragments'):
            pieces=json.loads(raw)
            keep_whole=technical(pieces,rid)
            if keep_whole:
                db.execute('INSERT OR REPLACE INTO preserved VALUES(?,?,?)',(rid,fid,keep_whole))
                count+=1
                continue
            for piece in pieces:
                key=dumps(piece)
                if key in seen:continue
                template=[]
                start=0
                for token in ATOM.finditer(piece):
                    template.extend(plan_span(piece[start:token.start()]))
                    template.append({'keep':token.group()});start=token.end()
                template.extend(plan_span(piece[start:]))
                db.execute('INSERT INTO pieces VALUES(?,?)',(key,dumps(template)))
                seen.add(key)
            count+=1
            if count%25000==0:
                db.commit();print(f'Prepared source fragments: {count}',flush=True)
    report={'fragments':count,'unique_pieces':len(seen),'segments':len(segments),
            'model_segments':db.execute("SELECT COUNT(*) FROM segments WHERE status='pending'").fetchone()[0],
            'glossary_segments':db.execute("SELECT COUNT(*) FROM segments WHERE status='glossary'").fetchone()[0]}
    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('prepared',dumps(report)))
    db.commit();db.close()
    (OUT/'source-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Full source plan:',report,flush=True)


def engine(model_name='ct2-int8'):
    sys.path.insert(0,str(BASE/'vendor'))
    handles=[];paths=[]
    for path in (BASE/'cuda-libs/nvidia').glob('*/bin'):
        handles.append(os.add_dll_directory(str(path)));paths.append(str(path))
    os.environ['PATH']=os.pathsep.join(paths+[os.environ.get('PATH','')])
    import ctranslate2
    import sentencepiece as spm
    model=BASE/'models/opus-en-zh'
    source=spm.SentencePieceProcessor(model_file=str(model/'original/source.spm'))
    target=spm.SentencePieceProcessor(model_file=str(model/'original/target.spm'))
    translator=ctranslate2.Translator(str(model/model_name),device='cuda',compute_type='int8_float16',
                                    inter_threads=1,intra_threads=4,max_queued_batches=4)
    return translator,source,target,handles


def translate(limit=0):
    prepare()
    db=connect()
    configure_decoder(db)
    validation=json.loads((OUT/'decoder-filter-validation.json').read_text(encoding='utf-8'))
    if not validation['identical_outputs']:raise ValueError('Filtered decoder not verified')
    translator,source,target,handles=engine('ct2-int8-filtered')
    total=db.execute('SELECT COUNT(*) FROM segments').fetchone()[0]
    completed=db.execute("SELECT COUNT(*) FROM segments WHERE status!='pending'").fetchone()[0]
    started=time.monotonic();new=0;last_report=0
    # Short/name entries are first; larger narrative entries follow, all checkpointed.
    while True:
        if (OUT/'STOP').exists():print('Stopped at user-controlled checkpoint.',flush=True);break
        rows=db.execute("SELECT id,source FROM segments WHERE status='pending' ORDER BY length(source),id LIMIT 256").fetchall()
        if not rows:break
        if limit:rows=rows[:max(0,limit-new)]
        if not rows:break
        tokens=[['>>cmn_Hans<<']+source.encode(normalize_input(s),out_type=str) for _,s in rows]
        if any(len(t)>512 for t in tokens):raise ValueError('Input segment exceeds verified token bound')
        results=translator.translate_batch(tokens,beam_size=1,max_batch_size=4096,batch_type='tokens',
            max_input_length=512,max_decoding_length=384,disable_unk=True,no_repeat_ngram_size=4)
        updates=[]
        for (sid,text),result in zip(rows,results):
            value=target.decode(result.hypotheses[0]).strip()
            if re.search(r'\bquests?\b',text,re.I):value=value.replace('探险任务','任务').replace('探险','任务')
            flags=[]
            if not value or controls(value) or any(unicodedata.category(c)=='Co' for c in value):
                # Model-generated protocol characters are rejected, never blended
                # with the source's protected protocol atoms.
                flags.append('empty_or_added_controls')
            if len(result.hypotheses[0])>=384:flags.append('possible_truncation')
            if not HAN.search(value):flags.append('no_han_or_proper_name')
            status='error' if any(f in flags for f in ('empty_or_added_controls','possible_truncation')) else 'machine_draft'
            updates.append((value,status,','.join(flags),sid))
        db.executemany('UPDATE segments SET translation=?,status=?,qa=? WHERE id=?',updates)
        db.commit();new+=len(rows);completed+=len(rows)
        elapsed=time.monotonic()-started
        if elapsed-last_report>=15 or new<=256:
            state={'phase':'translating','completed_segments':completed,'total_segments':total,
                   'new_segments_this_run':new,'elapsed_seconds':round(elapsed,1),
                   'segments_per_second':round(new/max(elapsed,0.01),1),'deployment_enabled':False}
            tmp=OUT/'progress.tmp';tmp.write_text(json.dumps(state,indent=2),encoding='utf-8');tmp.replace(OUT/'progress.json')
            print(json.dumps(state),flush=True);last_report=elapsed
    counts=dict(db.execute('SELECT status,COUNT(*) FROM segments GROUP BY status'))
    (OUT/'segment-summary.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    print('Segment statuses:',counts,flush=True)
    db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('prepare','translate','refresh'))
    parser.add_argument('--limit',type=int,default=0)
    args=parser.parse_args()
    if args.command=='prepare':prepare()
    elif args.command=='refresh':refresh_templates()
    else:translate(args.limit)
