"""Prepare reviewed map overrides and visibly separate uncertain draft labels."""
import json
from pathlib import Path
import re
import sys
import math
import statistics

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent.parent))
from localization.maps.render_maps import bounds


def merge_labels(labels,terms):
    from localization.maps.match_labels import normalize
    def compound_key(value):return normalize(re.sub(r'\b(?:the|of)\b','',value,flags=re.I))
    lookup={compound_key(k):(k,v) for k,v in terms.items() if v}
    # Route prefixes are standalone OCR lines on many maps.
    for key,value in list(terms.items()):
        if value and not key.lower().startswith('to '):lookup[compound_key('To '+key)]=('To '+key,'前往'+value)
    for _ in range(len(labels)):
        proposals=[]
        for i,left in enumerate(labels):
            a=bounds(left['polygon'])
            for j,right in enumerate(labels):
                if i==j:continue
                b=bounds(right['polygon']);h=max(a[3]-a[1],b[3]-b[1])
                vertical=(-h*.65<=b[1]-a[3]<=h*1.35 and b[1]+b[3]>a[1]+a[3] and abs((a[0]+a[2]-b[0]-b[2])/2)<max(a[2]-a[0],b[2]-b[0])*.65)
                horizontal=(-2<=b[0]-a[2]<=h*1.8 and abs((a[1]+a[3]-b[1]-b[3])/2)<h*.65)
                if not (vertical or horizontal):continue
                key=compound_key(left['source']+' '+right['source'])
                if key not in lookup:continue
                distance=math.hypot((a[0]+a[2]-b[0]-b[2])/2,(a[1]+a[3]-b[1]-b[3])/2)
                proposals.append((distance,i,j,lookup[key]))
        if not proposals:break
        _,i,j,(english,chinese)=min(proposals);left,right=labels[i],labels[j]
        a,b=bounds(left['polygon']),bounds(right['polygon']);x1,y1,x2,y2=min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])
        merged=dict(left,source=english,text=english,chinese=chinese,
            polygon=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
            font_size=min(left['font_size'],right['font_size']),
            component_ids=left.get('component_ids',[left['label_id']])+right.get('component_ids',[right['label_id']]))
        labels=[v for k,v in enumerate(labels) if k not in (i,j)]+[merged]
    return labels


def main():
    inventory=json.loads((BASE/'inventory.json').read_text(encoding='utf-8'))
    matches=json.loads((BASE/'label-matches.json').read_text(encoding='utf-8'))
    overrides=json.loads((BASE/'map-overrides.json').read_text(encoding='utf-8'))
    extra=json.loads((BASE/'extra-labels.json').read_text(encoding='utf8')) if (BASE/'extra-labels.json').exists() else {}
    for rid,rows in json.loads((BASE/'qa-additions.json').read_text(encoding='utf8')).items():extra.setdefault(rid,[]).extend(rows)
    corrections=json.loads((BASE/'ocr-corrections.json').read_text(encoding='utf-8'))
    exclusions=json.loads((BASE/'ocr-exclusions.json').read_text(encoding='utf8'))['excluded_raw_indexes']
    from localization.maps.match_labels import normalize,visual_key
    glossary=json.loads((BASE/'glossary.json').read_text(encoding='utf8'))
    terms={}
    for correction in corrections.values():
        if not correction['discard']:terms[correction['english']]=correction['chinese']
    for rows in overrides.values():
        for row in rows:terms[row[0]]=row[1]
    terms.update(glossary)
    terms.update(json.loads((BASE/'compound-glossary.json').read_text(encoding='utf8')))
    exact={normalize(k):(k,v) for k,v in terms.items()}
    visual={visual_key(k):(k,v) for k,v in terms.items()}
    sources={r['id']:r for r in inventory['records'] if r['kind']=='map'}
    maps=[];counts={'reviewed_maps':0,'draft_maps':0,'reviewed_labels':0,'draft_labels':0};pending=[]
    for match in matches['records']:
        rid=match['resource_id'];name=rid[2:];raw=json.loads((BASE/'ocr'/(name+'.json')).read_text(encoding='utf-8'))
        protected=[dict(value,label_id=f'{name}:source:{i}',chinese='') for i,value in enumerate(raw['labels']) if i not in exclusions.get(name,[])]
        labels=[]
        manual=overrides.get(name,extra.get(name,[]))
        if manual:
            for index,row in enumerate(manual):
                source,chinese,ids=row[:3]
                if len(row)>3:b=row[3]
                else:
                    boxes=[bounds(raw['labels'][i]['polygon']) for i in ids]
                    b=[min(x[0] for x in boxes),min(x[1] for x in boxes),max(x[2] for x in boxes),max(x[3] for x in boxes)]
                polygon=[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]]
                heights=[]
                for raw_index in ids:
                    p=raw['labels'][raw_index]['polygon']
                    heights.append(min(math.dist(p[0],p[1]),math.dist(p[0],p[3])))
                font_size=min(23,max(12,round(statistics.median(heights)*.85))) if heights else 13
                labels.append({'label_id':f'{name}:reviewed:{index}','text':source,'chinese':chinese,
                    'polygon':polygon,'reviewed':True,'source_indexes':ids,'font_size':font_size,'protect_source':len(row)>3})
        if name in overrides:
            counts['reviewed_maps']+=1;counts['reviewed_labels']+=len(labels)
        else:
            for value in match['labels']:
                correction=corrections.get(name+':'+value['text'],corrections.get('*:'+value['text']))
                if correction:
                    if not correction['discard'] and correction['chinese']:
                        labels.append(dict(value,chinese=correction['chinese'],source=correction['english'],reviewed=True))
                    continue
                key=normalize(value['text']);vk=visual_key(value['text'])
                found=exact.get(key,visual.get(vk))
                chinese=found[1] if found else None
                english=found[0] if found else value.get('source',value['text'])
                if chinese is None and value['status']=='glossary-draft' and value.get('match_score',0)>=84:
                    chinese=value.get('chinese')
                if chinese is not None:
                    if chinese:labels.append(dict(value,chinese=chinese,source=english,reviewed=False))
                elif value['status']!='ocr-noise-review':pending.append(dict(value,map=rid))
            counts['draft_maps']+=1;counts['draft_labels']+=len(labels)
        # A manually supplied full name supersedes OCR fragments of the same
        # English name at that location, rather than adding duplicate Chinese.
        def words(text):return set(re.findall('[a-z]+',re.sub(r'\b(?:the|of)\b','',text.lower())))
        manual_labels=[x for x in labels if ':reviewed:' in x['label_id']]
        filtered=[]
        for label in labels:
            if label in manual_labels:filtered.append(label);continue
            a=bounds(label['polygon']);cx=(a[0]+a[2])/2;cy=(a[1]+a[3])/2
            parts=words(label.get('source',label['text']))
            covered=False
            for manual_label in manual_labels:
                b=bounds(manual_label['polygon'])
                if b[0]<=cx<=b[2] and b[1]<=cy<=b[3] and parts and parts<=words(manual_label['text']):covered=True;break
            if not covered:filtered.append(label)
        labels=filtered
        for label in labels:
            if 'font_size' not in label:
                heights=[]
                for raw_index in label.get('original_indexes',[]):
                    p=raw['labels'][raw_index]['polygon'];heights.append(min(math.dist(p[0],p[1]),math.dist(p[0],p[3])))
                label['font_size']=min(20,max(12,round(statistics.median(heights)*.85))) if heights else 13
            label['source']=label.get('source',label['text'])
            if label['chinese']=='前往':label['source']='To'
            elif label['chinese'].startswith('前往') and not label['source'].lower().startswith('to '):label['source']='To '+label['source']
        if name not in overrides:labels=merge_labels(labels,terms)
        maps.append({'resource_id':rid,'source_image_sha256':sources[rid]['source_image_sha256'],
            'source_payload_sha256':sources[rid]['source_payload_sha256'],'labels':protected+labels,
            'label_reviewed':name in overrides})
    result={'maps':len(maps),'all_labels_reviewed':counts['draft_maps']==0,'counts':counts,'deployed':False,'records':maps}
    (BASE/'prepared-labels.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (BASE/'pending-labels.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Pending labels:',len(pending))
    print(json.dumps(counts),flush=True)


if __name__=='__main__':main()
