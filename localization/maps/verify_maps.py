"""Independently verify every generated map without changing the game."""
import argparse,hashlib,json,struct,sys
from io import BytesIO
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent.parent))
from lotro_zh.map_resource import jpeg_texture
from localization.maps.render_maps import bounds,overlap,expanded


def load_payloads(manifest_path,expected_count=None):
    path=Path(manifest_path).resolve();base=path.parent
    manifest=json.loads(path.read_text(encoding='utf8'));records=manifest['records'];seen=set();result=[]
    if manifest['maps']!=len(records) or expected_count is not None and len(records)!=expected_count:
        raise ValueError('Map manifest count mismatch')
    for row in records:
        rid=row['id'];target=(base/row['file']).resolve()
        if rid in seen or not target.is_relative_to(base):raise ValueError('Duplicate/outside map payload')
        if row['group']!='client_local_English.dat':raise ValueError('Wrong map archive group')
        raw=target.read_bytes()
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:
            raise ValueError('Map payload hash mismatch')
        parsed,dimensions,_=jpeg_texture(raw)
        if parsed!=rid or list(dimensions)!=row['image_size']:raise ValueError('Map identity/size mismatch')
        seen.add(rid);result.append((row,raw))
    return manifest,result


def verify(base=BASE,source_dat=None):
    base=Path(base);output=base/'bilingual-draft'
    manifest,payloads=load_payloads(output/'manifest.json',218)
    inventory=json.loads((base/'inventory.json').read_text(encoding='utf8'))
    originals={r['id']:r for r in inventory['records'] if r['kind']=='map'}
    prepared=json.loads((base/'prepared-labels.json').read_text(encoding='utf8'))
    specs={int(r['resource_id'],16):r for r in prepared['records']}
    if {int(k,16) for k in originals}!={r['id'] for r,_ in payloads}:raise ValueError('Inventory coverage mismatch')
    annotation_count=0;min_font=100;largest_offset=0;far=[]
    for row,raw in payloads:
        rid=row['id'];name=f'{rid:08X}';spec=originals[f'0x{name}'];path=base/'originals'/(name+'.jpg')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=spec['source_image_sha256']:
            raise ValueError('Source JPEG changed')
        if row['source_sha256']!=spec['source_payload_sha256']:raise ValueError('Source payload hash changed')
        image=Image.open(output/(name+'.png')).convert('RGB');original=Image.open(path).convert('RGB')
        layout=json.loads((output/(name+'.layout.json')).read_text(encoding='utf8'))
        if image.size!=original.size or layout['layout_failures']:raise ValueError('Dimensions/layout failure')
        mask=Image.new('L',image.size);draw=ImageDraw.Draw(mask);boxes=[]
        protected=[expanded(bounds(v['polygon']),1) for v in specs[rid]['labels'] if not v.get('chinese') or v.get('protect_source')]
        for label in layout['labels']:
            rect=label['annotation_box'];boxes.append(rect);draw.rectangle(rect,fill=255)
            if not(0<=rect[0]<rect[2]<=image.width and 0<=rect[1]<rect[3]<=image.height):raise ValueError('Out-of-bounds label')
            if any(overlap(rect,b)>0 for b in protected):raise ValueError('English label covered')
            a=bounds(label['polygon']);distance=((sum(rect[::2])/2-sum(a[::2])/2)**2+(sum(rect[1::2])/2-sum(a[1::2])/2)**2)**.5
            largest_offset=max(largest_offset,distance)
            if distance>140:far.append({'map':name,'chinese':label['chinese'],'distance':round(distance,1)})
            min_font=min(min_font,label['font_size'])
        if any(overlap(a,b)>0 for i,a in enumerate(boxes) for b in boxes[i+1:]):raise ValueError('Chinese overlap')
        delta=ImageChops.difference(image,original);outside=Image.new('RGB',image.size)
        outside.paste(delta,(0,0),ImageChops.invert(mask))
        if outside.getbbox():raise ValueError('Pixels outside annotation mask changed')
        # Compare to freshly encoded review PNG: the native JPEG has only the
        # expected lossy codec changes, not a different image or missing labels.
        jpeg=BytesIO();image.save(jpeg,format='JPEG',quality=100,subsampling=0,optimize=True)
        if raw[24:]!=jpeg.getvalue():raise ValueError('Native texture does not match review PNG')
        if len(boxes)!=row['chinese_labels']:raise ValueError('Rendered label count mismatch')
        annotation_count+=len(boxes)
    if source_dat:
        from lotro_zh.dat_reader import DatReader
        with DatReader(source_dat) as reader:
            entries={r.resource_id:r for r in reader.entries()}
            for row,_ in payloads:
                if hashlib.sha256(reader.content(entries[row['id']])).hexdigest()!=row['source_sha256']:
                    raise ValueError('Live original DAT map changed')
    report={'maps':len(payloads),'chinese_annotations':annotation_count,'all_original_dimensions_preserved':True,
        'source_JPEG_and_payload_hashes_verified':True,'pixels_outside_PNG_annotation_boxes_unchanged':True,
        'detected_English_text_boxes_preserved':True,'Chinese_overlap_count':0,'native_JPEG_payloads_verified':True,
        'minimum_font_size':min_font,'maximum_anchor_offset_pixels':round(largest_offset,1),'far_annotations':far,
        'source_DAT_verified':bool(source_dat),'game_tested':False,'deployed':False,
        'all_labels_manually_reviewed':False,'note':'OCR and visual overview cannot guarantee zero missed tiny labels; proper-name transliterations remain reviewable.'}
    (output/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='far_annotations'},ensure_ascii=False,indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-dat',type=Path);args=parser.parse_args();verify(source_dat=args.source_dat)
