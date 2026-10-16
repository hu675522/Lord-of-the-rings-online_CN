"""Deterministic bilingual labels on original map pixels; no game writes.

Chinese annotations avoid original label rectangles. Lossless review PNGs are
verified pixel-for-pixel outside the recorded annotation mask. JPEG payloads
retain the client's original dimensions and texture format.
"""
import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import struct
import sys

from PIL import Image,ImageDraw,ImageFont,ImageChops

BASE=Path(__file__).resolve().parent
FONT=Path(r'C:\Windows\Fonts\msyh.ttc')


def bounds(polygon):
    xs,ys=zip(*polygon)
    return (math.floor(min(xs)),math.floor(min(ys)),math.ceil(max(xs)),math.ceil(max(ys)))


def overlap(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def expanded(a,padding=2):
    return (a[0]-padding,a[1]-padding,a[2]+padding,a[3]+padding)


def layout_label(chinese,anchor,originals,placed,size):
    """Keep text inside the map and outside all existing English labels."""
    cx=(anchor[0]+anchor[2])/2;cy=(anchor[1]+anchor[3])/2
    for font_size in range(size,9,-1):
        font=ImageFont.truetype(str(FONT),font_size)
        box=font.getbbox(chinese,stroke_width=1)
        width=box[2]-box[0]+4;height=box[3]-box[1]+4
        candidates=[]
        for ring in range(0,8):
            gap=3+ring*(height+3)
            positions=[(cx-width/2,anchor[3]+gap),(cx-width/2,anchor[1]-height-gap),
                       (anchor[2]+gap,cy-height/2),(anchor[0]-width-gap,cy-height/2)]
            for x,y in positions:
                for dx in (0,-width*.35,width*.35):
                    left=round(x+dx);top=round(y);rect=(left,top,left+width,top+height)
                    if left<5 or top<5 or rect[2]>size_bounds[0]-5 or rect[3]>size_bounds[1]-5:continue
                    if any(overlap(expanded(rect,1),other)>0 for other in originals):continue
                    if any(overlap(expanded(rect,2),other)>0 for other in placed):continue
                    distance=math.hypot((rect[0]+rect[2])/2-cx,(rect[1]+rect[3])/2-cy)
                    candidates.append((distance,rect,font,box,font_size))
            if candidates:return min(candidates,key=lambda x:x[0])[1:]
    raise ValueError('No collision-free label position: '+chinese)


def render(source,labels,destination):
    global size_bounds
    original=Image.open(source).convert('RGB');size_bounds=original.size
    image=original.copy();draw=ImageDraw.Draw(image)
    mask=Image.new('L',original.size);mask_draw=ImageDraw.Draw(mask)
    originals=[expanded(bounds(r['polygon']),1) for r in labels if r.get('polygon') and (not r.get('chinese') or r.get('protect_source'))]
    placed=[];records=[];failures=[]
    # Long/large labels are placed first; smaller labels use the remaining gaps.
    work=[r for r in labels if r.get('chinese')]
    work.sort(key=lambda r:(-min(23,max(12,round((bounds(r['polygon'])[3]-bounds(r['polygon'])[1])*.65))),-len(r['chinese'])))
    for label in work:
        chinese=label['chinese'];anchor=bounds(label['polygon'])
        font_size=label.get('font_size',min(20,max(12,round((anchor[3]-anchor[1])*.55))))
        try:rect,font,box,font_size=layout_label(chinese,anchor,originals,placed,font_size)
        except ValueError as error:
            failures.append({'label_id':label['label_id'],'reason':str(error)});continue
        # PIL bbox offsets are included so the recorded mask encloses all pixels.
        x=rect[0]+2-box[0];y=rect[1]+2-box[1]
        draw.text((x,y),chinese,font=font,fill=(255,242,205),stroke_width=1,stroke_fill=(70,24,12))
        mask_draw.rectangle(rect,fill=255);placed.append(rect)
        records.append(dict(label,annotation_box=list(rect),font_size=font_size))
    difference=ImageChops.difference(original,image)
    outside=Image.new('RGB',original.size)
    outside.paste(difference,(0,0),ImageChops.invert(mask))
    if outside.getbbox() is not None:raise ValueError('Pixels outside annotations changed')
    if any(overlap(r,rect)>0 for r in originals for rect in placed):raise ValueError('Original English text covered')
    if any(overlap(a,b)>0 for i,a in enumerate(placed) for b in placed[i+1:]):raise ValueError('Chinese label collision')
    destination.parent.mkdir(parents=True,exist_ok=True)
    image.save(destination,format='PNG',optimize=True)
    jpeg=BytesIO();image.save(jpeg,format='JPEG',quality=100,subsampling=0,optimize=True)
    jpeg=jpeg.getvalue()
    if Image.open(BytesIO(jpeg)).size!=original.size:raise ValueError('JPEG dimensions changed')
    return {'image_size':list(original.size),'labels':records,'layout_failures':failures,
            'pixels_outside_annotation_boxes_unchanged':True,'original_English_rectangles_unchanged':True,
            'annotation_collisions':0},jpeg


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids',default='');parser.add_argument('--draft',action='store_true')
    args=parser.parse_args()
    dataset=json.loads((BASE/'prepared-labels.json').read_text(encoding='utf-8'))
    if not args.draft and not dataset.get('all_labels_reviewed'):
        raise ValueError('Unreviewed labels require an explicit --draft run')
    selected={x.upper().removeprefix('0X') for x in args.ids.split(',') if x}
    output=BASE/('bilingual-draft' if args.draft else 'bilingual')
    payloads=output/'records';payloads.mkdir(parents=True,exist_ok=True)
    summary=[]
    for item in dataset['records']:
        rid=int(item['resource_id'],16);name=f'{rid:08X}'
        if selected and name not in selected:continue
        source=BASE/'originals'/(name+'.jpg')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=item['source_image_sha256']:
            raise ValueError('Original map changed: '+name)
        report,jpeg=render(source,item['labels'],output/(name+'.png'))
        if report['layout_failures']:
            raise ValueError('Layout failed: '+json.dumps(report['layout_failures'],ensure_ascii=False))
        if not report['labels']:raise ValueError('No Chinese labels rendered: '+name)
        # Keep the same JPEG texture container layout; no archive opens/writes.
        raw=struct.pack('<6I',rid,15,0,0,500,len(jpeg))+jpeg
        path=payloads/(name+'.bin');path.write_bytes(raw)
        (output/(name+'.layout.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        summary.append({'id':rid,'source_sha256':item['source_payload_sha256'],'file':'records/'+path.name,
            'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'group':'client_local_English.dat',
            'chinese_labels':len(report['labels']),'image_size':report['image_size'],
            'pixels_outside_annotation_boxes_unchanged':True,'original_English_rectangles_unchanged':True})
        print(f'Bilingual map {len(summary)}: {name}, {len(report["labels"])} Chinese labels',flush=True)
    manifest={'format':'LOTRO JPEG texture resources with deterministic bilingual labels',
        'maps':len(summary),'all_labels_reviewed':dataset.get('all_labels_reviewed',False),
        'game_tested':False,'deployed':False,'records':summary}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'maps_rendered':len(summary),'labels':sum(r['chinese_labels'] for r in summary),'deployed':False},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
