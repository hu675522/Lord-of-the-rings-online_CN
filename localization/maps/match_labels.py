"""Reconcile OCR with source spellings before translating map labels."""
import collections
import json
from pathlib import Path
import re
import sys
import unicodedata

BASE = Path(__file__).resolve().parent


def normalize(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return re.sub('[^a-z0-9]', '', ''.join(c for c in text if not unicodedata.combining(c)))


def visual_key(text):
    # The map's uncial typeface consistently confuses these glyph groups.
    return normalize(text).translate(str.maketrans({'b':'h','c':'t','d':'n','v':'u','0':'o','1':'i','l':'i'}))


def group_known_lines(labels, known):
    groups=[dict(value,original_indexes=[i]) for i,value in enumerate(labels)]
    def bounds(item):
        xs,ys=zip(*item['polygon'])
        return min(xs),min(ys),max(xs),max(ys)
    for _ in range(3):
        changed=False
        for i,left in enumerate(groups):
            a=bounds(left)
            for j,right in enumerate(groups):
                if i==j:continue
                b=bounds(right)
                vertical=(0<=b[1]-a[3]<=max(a[3]-a[1],b[3]-b[1])*1.3 and
                          abs((a[0]+a[2]-b[0]-b[2])/2)<max(a[2]-a[0],b[2]-b[0])*.65)
                horizontal=(0<=b[0]-a[2]<=max(a[3]-a[1],b[3]-b[1])*1.8 and
                            abs((a[1]+a[3]-b[1]-b[3])/2)<max(a[3]-a[1],b[3]-b[1])*.65)
                text=left['text']+' '+right['text']
                if not (vertical or horizontal) or visual_key(text) not in known:continue
                x1,y1,x2,y2=min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])
                merged={'text':text,'score':min(left['score'],right['score']),
                    'polygon':[[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                    'original_indexes':left['original_indexes']+right['original_indexes']}
                groups=[value for k,value in enumerate(groups) if k not in (i,j)]+[merged]
                changed=True
                break
            if changed:break
        if not changed:break
    return groups


def main():
    sys.path.insert(0, str(BASE / 'vendor'))
    from rapidfuzz import process, fuzz
    glossary = json.loads((BASE / 'glossary.json').read_text(encoding='utf-8'))
    candidates = json.loads((BASE / 'catalog-name-candidates.json').read_text(encoding='utf-8'))
    references = {}
    for row in candidates:
        source = row['source']
        if len(source.split()) > 5 or re.search(r'\b(?:you|your|this|that|have|does|has|have|is|are|must|cannot|someone)\b', source, re.I):
            continue
        target = row['chinese']
        if len(target) > 35 or re.search(r'(.{2,6})\1\1', target):
            continue
        references[normalize(source)] = {'source': source, 'chinese': target, 'provenance': 'existing-text-draft'}
    domain = {}
    for source, target in glossary.items():
        value = {'source': source, 'chinese': target, 'provenance': 'map-glossary'}
        references[normalize(source)] = value
        domain[normalize(source)] = value
    choices = list(references)
    domain_choices = list(domain)
    visual_domain=collections.defaultdict(list)
    visual_references=collections.defaultdict(list)
    for key,value in domain.items():visual_domain[visual_key(value['source'])].append(value)
    for key,value in references.items():visual_references[visual_key(value['source'])].append(value)
    cache = {}
    def match(text):
        if text in cache:
            return cache[text]
        core = text.strip(' ()[].,!')
        prefix = ''
        found = re.match(r'^(?:to|co)\s+(?:(?:the|che|cbe)\s+)?(.+)', core, re.I)
        if found:
            core = found[1]
            prefix = '前往'
        key = normalize(core)
        visual=visual_key(core)
        if visual in visual_domain and len(visual_domain[visual])==1:
            result=dict(visual_domain[visual][0],match_score=100.,second_score=0.,prefix=prefix)
        elif key in references:
            result = dict(references[key], match_score=100., second_score=0., prefix=prefix)
        elif visual in visual_references and len(visual_references[visual])==1:
            result=dict(visual_references[visual][0],match_score=96.,second_score=0.,prefix=prefix)
        else:
            ds = process.extract(key, domain_choices, scorer=fuzz.ratio, limit=2, score_cutoff=68.)
            cs = process.extract(key, choices, scorer=fuzz.ratio, limit=2, score_cutoff=70.)
            selected = ds if ds and ds[0][1] >= 80 and (not cs or ds[0][1] >= cs[0][1]-8.) else cs
            refs = domain if selected is ds else references
            if selected:
                result = dict(refs[selected[0][0]], match_score=round(selected[0][1],2),
                              second_score=round(selected[1][1],2) if len(selected)>1 else 0., prefix=prefix)
            else:
                result = None
        cache[text] = result
        return result
    maps = []
    counts = collections.Counter()
    for path in sorted((BASE / 'ocr').glob('*.json')):
        item = json.loads(path.read_text(encoding='utf-8'))
        labels = []
        for index, raw in enumerate(group_known_lines(item['labels'],visual_domain)):
            text = raw['text']
            key = normalize(text)
            record = dict(raw, label_id=f'{path.stem}:{index}', status='unresolved')
            if len(key)<3 or not re.search('[a-z]',key) or raw['score']<.52:
                record['status']='ocr-noise-review'
            else:
                best = match(text)
                if best:
                    record.update(best)
                    record['chinese'] = best['prefix'] + best['chinese']
                    record['status'] = 'glossary-draft' if best['provenance']=='map-glossary' else 'catalog-draft'
                    if best['match_score']<84 or (best['second_score']>0 and best['match_score']-best['second_score']<4 and best['match_score']!=100):
                        record['status']='match-review'
            counts[record['status']]+=1
            labels.append(record)
        maps.append({'resource_id':item['resource_id'],'source_image_sha256':item['source_image_sha256'],
                     'width':item['width'],'height':item['height'],'labels':labels})
    report = {'maps':len(maps),'counts':dict(counts),'labels_review_complete':False,'deployed':False,'records':maps}
    (BASE/'label-matches.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=[]
    for item in maps:
        lines.append('\n'+item['resource_id'])
        for label in item['labels']:
            if label['status']=='ocr-noise-review':continue
            lines.append(f"{label['label_id']} | {label['text']} | {label.get('source','?')} => {label.get('chinese','?')} | {label.get('match_score',0)} {label['status']}")
    (BASE/'label-review.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'maps':len(maps),'counts':dict(counts),'unique_OCR_strings_matched':len(cache)},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
